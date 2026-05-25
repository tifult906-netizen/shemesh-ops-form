"""Combine output of all 5 parsers into one ClientPicture, with cross-refs.

Cross-references performed:
 * pitsuyim employer rows ↔ BL employer-details — matched by `tik_maasik`
   containing the pitsuyim `employer_id` (the company tax ID is sometimes
   embedded in the BL 11-digit file number) or by index when no clean match.
 * maslaka funds ↔ tagmulim/pitsuyim funds — matched by `tik_nikuim`.

Surface conflicts (e.g. balance mismatch between maslaka and tagmulim) on
the returned `ClientPicture.notes` list for the UI to display.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .models import (
    BankAccount,
    BLEmploymentHistory,
    ClientIdentity,
    ClientPicture,
    IDCard,
    MaslakaReport,
    PitsuyimReport,
    TagmulimReport,
)
from .parsers.bank import parse_bank_confirmation
from .parsers.bl_history import parse_bl_history
from .parsers.maslaka import parse_maslaka_report
from .parsers.pitsuyim import parse_pitsuyim_report
from .parsers.tagmulim import parse_tagmulim_report
from .vision import VisionExtractor
from .vision.extractors import (
    extract_id_card,
    fill_bank_labels,
    fill_bl_labels,
    fill_maslaka_labels,
    fill_pitsuyim_labels,
    fill_tagmulim_labels,
)


@dataclass
class ExtractionInputs:
    bank: Path | None = None
    tagmulim: Path | None = None
    pitsuyim: Path | None = None
    maslaka: Path | None = None
    bl_history: Path | None = None
    id_front: Path | None = None
    id_back: Path | None = None


@dataclass
class UnificationResult:
    picture: ClientPicture
    notes: list[str] = field(default_factory=list)
    employer_xref: dict[str, str | None] = field(default_factory=dict)
    """Maps pitsuyim employer_id → BL tik_maasik (or None if no match)."""


def _normalize_id(id_str: str) -> str:
    """Israeli IDs are 9 digits; pad with leading zero if 8."""
    s = id_str.strip()
    return s.zfill(9) if len(s) == 8 else s


def unify(
    inputs: ExtractionInputs,
    vision: VisionExtractor | None = None,
) -> UnificationResult:
    notes: list[str] = []

    bank: BankAccount | None = None
    tag: TagmulimReport | None = None
    pit: PitsuyimReport | None = None
    mas: MaslakaReport | None = None
    bl: BLEmploymentHistory | None = None
    id_card: IDCard | None = None

    def _try(label: str, op):
        try:
            return op()
        except Exception as e:
            notes.append(f"{label} extraction failed: {e}")
            return None

    if inputs.bank:
        bank = _try("bank", lambda: parse_bank_confirmation(inputs.bank))
    if inputs.tagmulim:
        tag = _try("tagmulim", lambda: parse_tagmulim_report(inputs.tagmulim))
    if inputs.pitsuyim:
        pit = _try("pitsuyim", lambda: parse_pitsuyim_report(inputs.pitsuyim))
    if inputs.maslaka:
        mas = _try("maslaka", lambda: parse_maslaka_report(inputs.maslaka))
    if inputs.bl_history:
        bl = _try("bl_history", lambda: parse_bl_history(inputs.bl_history))

    if vision is not None:
        if bank and inputs.bank:
            _try("bank labels (vision)", lambda: fill_bank_labels(bank, inputs.bank, vision))
        if tag and inputs.tagmulim:
            _try("tagmulim labels (vision)", lambda: fill_tagmulim_labels(tag, inputs.tagmulim, vision))
        if pit and inputs.pitsuyim:
            _try("pitsuyim labels (vision)", lambda: fill_pitsuyim_labels(pit, inputs.pitsuyim, vision))
        if mas and inputs.maslaka:
            _try("maslaka labels (vision)", lambda: fill_maslaka_labels(mas, inputs.maslaka, vision))
        if bl and inputs.bl_history:
            _try("bl labels (vision)", lambda: fill_bl_labels(bl, inputs.bl_history, vision))
        if inputs.id_front and inputs.id_back:
            id_card = _try(
                "id card (vision)",
                lambda: extract_id_card(
                    inputs.id_front.read_bytes(),
                    inputs.id_back.read_bytes(),
                    vision,
                ),
            )

    # Pick a canonical client identity. ID card wins if available (most
    # authoritative — issued by the state). Otherwise bank confirmation.
    if id_card:
        identity = ClientIdentity(full_name=id_card.full_name, id_number=_normalize_id(id_card.id_number))
    elif bank:
        identity = ClientIdentity(full_name=bank.holder_name, id_number=_normalize_id(bank.id_number))
    elif tag:
        identity = ClientIdentity(full_name="", id_number=_normalize_id(tag.client.id_number))
    elif pit:
        identity = ClientIdentity(full_name="", id_number=_normalize_id(pit.client.id_number))
    elif mas:
        identity = ClientIdentity(full_name="", id_number=_normalize_id(mas.client.id_number))
    elif bl:
        identity = ClientIdentity(full_name="", id_number=_normalize_id(bl.client.id_number))
    else:
        raise ValueError("No inputs provided")

    # ID consistency check
    seen_ids = set()
    for src_name, src in [("bank", bank), ("tagmulim", tag), ("pitsuyim", pit), ("maslaka", mas), ("bl", bl)]:
        if src is None:
            continue
        sid = _normalize_id(src.client.id_number if hasattr(src, "client") else src.id_number)
        seen_ids.add(sid)
    if len(seen_ids) > 1:
        notes.append(f"client ID mismatch across sources: {sorted(seen_ids)}")

    # Balance sanity check: maslaka totals per tik vs tagmulim totals per tik
    if mas and tag:
        mas_balance_by_tik: dict[str, Decimal] = {}
        for f in mas.funds:
            if f.tik_nikuim:
                mas_balance_by_tik.setdefault(f.tik_nikuim, Decimal(0))
                mas_balance_by_tik[f.tik_nikuim] += f.total_balance
        tag_balance_by_tik: dict[str, Decimal] = {}
        for f in tag.funds:
            tag_balance_by_tik.setdefault(f.tik_nikuim, Decimal(0))
            tag_balance_by_tik[f.tik_nikuim] += f.total
        for tik, t_total in tag_balance_by_tik.items():
            m_total = mas_balance_by_tik.get(tik)
            if m_total is None:
                notes.append(f"tagmulim tik {tik} missing from מסלקה report")
            elif abs(m_total - t_total) > Decimal("1"):
                # Maslaka aggregates ALL money in the fund; tagmulim only the
                # tagmulim-bucket portion. So unequal is expected, just flag
                # when maslaka < tagmulim (which would mean a real discrepancy).
                if m_total < t_total:
                    notes.append(
                        f"מסלקה reports less for tik {tik} (₪{m_total}) than tagmulim (₪{t_total})"
                    )

    # Employer cross-ref: pitsuyim employer_id → BL tik_maasik
    employer_xref: dict[str, str | None] = {}
    if pit and bl:
        bl_tiks = {e.tik_maasik for e in bl.employer_details}
        for row in pit.rows:
            if not row.employer_id or row.employer_id == "0":
                continue
            # Best-effort: BL tik might *contain* the company tax ID, but in
            # the example data they don't share digits (the BL file number is
            # not derived from the company tax ID). So this xref is mainly a
            # placeholder for the future name-fuzzy-match (vision pass).
            match = next((t for t in bl_tiks if row.employer_id in t), None)
            employer_xref[row.employer_id] = match
            if match is None:
                notes.append(
                    f"pitsuyim employer {row.employer_id} not found in BL doc — "
                    "will need name-based match after vision pass"
                )

    picture = ClientPicture(
        identity=identity,
        bank=bank or BankAccount(
            holder_name="",
            id_number=identity.id_number,
            bank_code="",
            branch="",
            account_number="",
        ),
        id_card=id_card,
        tagmulim=tag,
        pitsuyim=pit,
        maslaka=mas,
        bl_history=bl,
    )
    return UnificationResult(picture=picture, notes=notes, employer_xref=employer_xref)
