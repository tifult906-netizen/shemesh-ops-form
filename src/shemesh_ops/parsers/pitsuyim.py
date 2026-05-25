"""Parser for 'דוח יתרות כספי פיצויים' (pitsuyim balances report).

Per-row data is fund × employer. Layout (right-to-left in source, so listed
here in left-to-right extraction order):

    [4 amounts] [optional date DD/MM/YYYY] [employer_id 9-digit or '0']
    [garbled employer/kupa name] [tik_nikuim 9-digit]

The 4 amounts, from extracted (leftmost) to rightmost in source:
    shavi_pitsuyim_per_employer | retzef_pitsuyim_or_maasikim |
    retzef_kitzba_post_2000 | retzef_kitzba_pre_2000
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from ..models import ClientIdentity, PitsuyimEmployerRow, PitsuyimReport
from ._pdf_utils import extract_raw_text, parse_dmy

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
AMOUNT_RE = re.compile(r"₪([\d,]+\.\d{2})")
DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
NINE_DIGIT_RE = re.compile(r"\b(\d{9})\b")


def _to_decimal(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def parse_pitsuyim_report(pdf_path: Path | str) -> PitsuyimReport:
    text = extract_raw_text(pdf_path)
    lines = text.split("\n")

    uuid_match = UUID_RE.search(text)
    request_id = uuid_match.group(0) if uuid_match else None

    info_matches = re.findall(r"(\d{2}/\d{2}/\d{4})\s*:", text)
    information_date = parse_dmy(info_matches[1]) if len(info_matches) >= 2 else None

    client_id_match = re.search(r"\b(2\d{7,8})\b", text)
    if not client_id_match:
        raise ValueError("Client ID not found in pitsuyim report")
    client_id = client_id_match.group(1)

    rows: list[PitsuyimEmployerRow] = []
    grand_total: Decimal | None = None

    for line in lines:
        amounts = AMOUNT_RE.findall(line)
        nine_digits = NINE_DIGIT_RE.findall(line)
        if len(amounts) >= 4 and len(nine_digits) >= 1:
            # Real data row (fund × employer)
            tik = nine_digits[-1]
            # Strip client ID and tik from candidate employer IDs to avoid
            # confusing them with a real employer.
            employer_id_candidates = [
                d for d in nine_digits[:-1] if d != client_id
            ]
            employer_id = employer_id_candidates[0] if employer_id_candidates else None

            date_match = DATE_RE.search(line)
            employment_start = parse_dmy(date_match.group(1)) if date_match else None

            shavi = _to_decimal(amounts[0])
            retzef_pitsuyim = _to_decimal(amounts[1])
            retzef_kitzba_post = _to_decimal(amounts[2])
            retzef_kitzba_pre = _to_decimal(amounts[3])

            rows.append(
                PitsuyimEmployerRow(
                    tik_nikuim=tik,
                    kupa_name="",  # vision pass
                    employer_name="",  # vision pass
                    employer_id=employer_id,
                    employment_start_date=employment_start,
                    retzef_kitzba_pre_2000=retzef_kitzba_pre,
                    retzef_kitzba_post_2000=retzef_kitzba_post,
                    retzef_pitsuyim_or_maasikim=retzef_pitsuyim,
                    shavi_pitsuyim_per_employer=shavi,
                )
            )
        elif len(amounts) == 1 and not nine_digits and grand_total is None:
            grand_total = _to_decimal(amounts[0])

    if grand_total is None:
        grand_total = sum((r.shavi_pitsuyim_per_employer for r in rows), Decimal(0))

    return PitsuyimReport(
        client=ClientIdentity(full_name="", id_number=client_id),
        information_date=information_date,
        request_id=request_id,
        rows=rows,
        grand_total=grand_total,
    )
