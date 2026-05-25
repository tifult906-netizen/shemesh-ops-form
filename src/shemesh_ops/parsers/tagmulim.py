"""Parser for 'דוח יתרות כספי תגמולים' (tagmulim balances report from המסלקה הפנסיונית).

Hebrew labels (kupa name, member status) come from a custom-CID font and don't
decode from the text layer. Numeric fields (tik_nikuim, balances per bucket,
totals) extract cleanly via regex.

Columns in the report (right-to-left in source, so first-extracted = total):
  סה"כ צבירה | קצבתי חייב | קיצבתי לפני 2000 או לפני 1997 | הוני

For pension funds the הוני column shows a placeholder ("רכיב לא רלוונטי...")
instead of a number, so fund rows have 3 numeric amounts. The grand-total row
has 4 amounts.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from ..models import ClientIdentity, TagmulimFundRow, TagmulimReport
from ._pdf_utils import extract_raw_text, parse_dmy

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
AMOUNT_RE = re.compile(r"₪([\d,]+\.\d{2})")
TIK_RE = re.compile(r"\b(\d{9})\s*$")


def _to_decimal(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def parse_tagmulim_report(pdf_path: Path | str) -> TagmulimReport:
    text = extract_raw_text(pdf_path)
    lines = text.split("\n")

    uuid_match = UUID_RE.search(text)
    request_id = uuid_match.group(0) if uuid_match else None

    # Two dates appear with ":" suffix — generation date (top of page) and
    # validity date (header table). Validity date is the second occurrence.
    info_matches = re.findall(r"(\d{2}/\d{2}/\d{4})\s*:", text)
    information_date = parse_dmy(info_matches[1]) if len(info_matches) >= 2 else None

    client_id_match = re.search(r"\b(2\d{7,8})\b", text)
    if not client_id_match:
        raise ValueError("Client ID not found in tagmulim report")
    client_id = client_id_match.group(1)

    funds: list[TagmulimFundRow] = []
    grand_total: Decimal | None = None

    for line in lines:
        amounts = AMOUNT_RE.findall(line)
        if not amounts:
            continue
        tik_match = TIK_RE.search(line)

        if tik_match:
            tik = tik_match.group(1)
            # 3 amounts: kitzbati-pre-2000, kitzbati-chayav, total
            # (the 4th column הוני is a placeholder text for pension funds)
            # Amounts appear in left-to-right order in extracted text = RTL in
            # source, so first extracted = leftmost = total.
            if len(amounts) >= 3:
                total = _to_decimal(amounts[0])
                chayav = _to_decimal(amounts[1])
                pre_2000 = _to_decimal(amounts[2])
                hony = _to_decimal(amounts[3]) if len(amounts) >= 4 else Decimal(0)
                funds.append(
                    TagmulimFundRow(
                        tik_nikuim=tik,
                        kupa_name="",  # vision pass
                        member_status=None,  # vision pass
                        hony=hony,
                        kitzbati_pre_2000_or_1997=pre_2000,
                        kitzbati_chayav=chayav,
                        total=total,
                    )
                )
        else:
            # No tik on this line — could be the grand-total row (4 amounts).
            if len(amounts) >= 4 and grand_total is None:
                grand_total = _to_decimal(amounts[0])

    if grand_total is None:
        gt_match = re.search(r"₪([\d,]+\.\d{2})\s*:?\s*$", text, re.MULTILINE)
        if gt_match:
            grand_total = _to_decimal(gt_match.group(1))
        else:
            grand_total = sum((f.total for f in funds), Decimal(0))

    return TagmulimReport(
        client=ClientIdentity(full_name="", id_number=client_id),
        information_date=information_date,
        request_id=request_id,
        funds=funds,
        grand_total=grand_total,
    )
