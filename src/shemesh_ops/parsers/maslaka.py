"""Parser for 'דוח מסלקה' (full pension clearing-house report).

11-page report. Pages 3-6 carry the per-fund detail in column-per-fund tables.
Pages 1-2 (summary + insurance), 7-8 (contribution history), 9 (insurance
summary), 10-11 (blank/legend) are not used in this MVP.

Hebrew labels are CID-encoded and don't decode from the text layer (and on
pages 1-8 they're also reversed letter-by-letter — a separate quirk). So
labels are deferred to the vision pass. Numeric fields extract cleanly.

Column-detection: per page we count integer/decimal/date values per line,
take the most common count as the column count, then per column index we
collect the values found on each value-row.

Date assignment per column (walking lines from bottom up, skipping future
dates that represent קה"ש unlock or projected-pension dates):
    - 1st date encountered = information_date
    - 2nd date encountered = first_join_date (if 3 dates present) OR
                              plan_start_date (if 2 dates present)
    - 3rd date encountered = plan_start_date
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pdfplumber

from ..models import ClientIdentity, MaslakaFund, MaslakaReport
from ._pdf_utils import parse_dmy

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
AMOUNT_RE = re.compile(r"₪\s*([\d,]+\.\d{2})")
DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
NINE_DIGIT_RE = re.compile(r"\b(\d{9})\b")
INT_RE = re.compile(r"\b(\d{3,15})\b")  # for policy numbers / AMA

DETAIL_PAGE_INDICES = [2, 3, 4, 5]  # pages 3, 4, 5, 6


def _line_values(line: str) -> list[str]:
    """Pull amounts, dates, and bare integers from a line in extraction order."""
    values: list[tuple[int, str]] = []
    for m in AMOUNT_RE.finditer(line):
        values.append((m.start(), m.group(0)))
    for m in DATE_RE.finditer(line):
        values.append((m.start(), m.group(0)))
    # Integers that aren't part of an amount/date.
    consumed = {(s, e) for s, e in (m.span() for m in AMOUNT_RE.finditer(line))} | {
        (s, e) for s, e in (m.span() for m in DATE_RE.finditer(line))
    }
    for m in INT_RE.finditer(line):
        s, e = m.span()
        if any(cs <= s and e <= ce for cs, ce in consumed):
            continue
        values.append((s, m.group(1)))
    values.sort()
    return [v for _, v in values]


def _amounts(line: str) -> list[Decimal]:
    return [Decimal(m.group(1).replace(",", "")) for m in AMOUNT_RE.finditer(line)]


def _dates(line: str) -> list[date]:
    return [parse_dmy(m.group(1)) for m in DATE_RE.finditer(line)]


def _ints(line: str) -> list[str]:
    """Integers on the line excluding any inside amounts/dates."""
    consumed: list[tuple[int, int]] = []
    for m in AMOUNT_RE.finditer(line):
        consumed.append(m.span())
    for m in DATE_RE.finditer(line):
        consumed.append(m.span())
    out: list[str] = []
    for m in INT_RE.finditer(line):
        s, e = m.span()
        if any(cs <= s and e <= ce for cs, ce in consumed):
            continue
        out.append(m.group(1))
    return out


def _column_count(lines: list[str]) -> int:
    """Most common count of (any) values across value-bearing lines."""
    counts: list[int] = []
    for line in lines:
        n = len(_line_values(line))
        if n > 0:
            counts.append(n)
    if not counts:
        return 0
    return Counter(counts).most_common(1)[0][0]


def _extract_funds_from_page(text: str, information_date_doc: date | None) -> list[MaslakaFund]:
    lines = text.split("\n")
    col_count = _column_count(lines)
    if col_count == 0:
        return []

    amount_rows: list[list[Decimal]] = []
    date_rows: list[list[date]] = []
    int_rows: list[list[str]] = []

    for line in lines:
        a = _amounts(line)
        d = _dates(line)
        i = _ints(line)
        if len(a) == col_count and not d and not i:
            amount_rows.append(a)
        elif len(d) == col_count and not a and not i:
            date_rows.append(d)
        elif len(i) == col_count and not a and not d:
            int_rows.append(i)

    funds: list[MaslakaFund] = []
    for col in range(col_count):
        total_balance = amount_rows[0][col] if amount_rows else Decimal(0)

        # Filter far-future dates (קה"ש unlock, life-insurance maturity,
        # pension eligibility) — anything > doc info_date + 1 year.
        future_cutoff = (
            information_date_doc + timedelta(days=365) if information_date_doc else None
        )
        col_dates = [
            row[col] for row in date_rows
            if future_cutoff is None or row[col] <= future_cutoff
        ]
        # Walk from bottom up — gives us [info_date, first_join, plan_start].
        rev = list(reversed(col_dates))
        information_date = rev[0] if rev else None
        plan_start_date: date | None
        first_join_date: date | None
        if len(rev) >= 3:
            first_join_date = rev[1]
            plan_start_date = rev[2]
        elif len(rev) == 2:
            first_join_date = None
            plan_start_date = rev[1]
        else:
            first_join_date = None
            plan_start_date = None

        col_ints = [row[col] for row in int_rows]
        nine_digit_ints = [v for v in col_ints if len(v) == 9]
        tik_nikuim = nine_digit_ints[-1] if nine_digit_ints else None
        # ת.ח חברה מנהלת = the 9-digit before the tik row.
        mgmt_tax_id = nine_digit_ints[-2] if len(nine_digit_ints) >= 2 else None
        # AMA number = 3-digit integer near the bottom.
        small_ints = [v for v in col_ints if 3 <= len(v) <= 4]
        ama_number = small_ints[-1] if small_ints else None
        # Policy number = the first integer-only row's value at this column.
        policy_number = col_ints[0] if col_ints else ""

        funds.append(
            MaslakaFund(
                management_company="",  # vision pass
                product_category=_infer_category_from_tik(tik_nikuim, page_dates=col_dates),
                product_type_label=None,
                policy_number=policy_number,
                status=None,  # vision pass
                total_balance=total_balance,
                plan_start_date=plan_start_date,
                first_join_date=first_join_date,
                information_date=information_date,
                tik_nikuim=tik_nikuim,
                ama_number=ama_number,
                management_company_tax_id=mgmt_tax_id,
            )
        )
    return funds


# Tik-nikuim prefix → product category. Heuristic; vision pass will refine.
_TIK_CATEGORY_PREFIX = {
    "935": "new_pension",
    "936": "study_fund",
    "930": "managers_insurance",  # could also be pure-risk policy
}


def _infer_category_from_tik(tik: str | None, page_dates: list[date]) -> str:
    if not tik:
        return "other"
    prefix = tik[:3]
    cat = _TIK_CATEGORY_PREFIX.get(prefix)
    if cat:
        return cat
    return "other"


def parse_maslaka_report(pdf_path: Path | str) -> MaslakaReport:
    funds: list[MaslakaFund] = []
    request_id: str | None = None
    client_id: str | None = None
    information_date: date | None = None

    with pdfplumber.open(str(pdf_path)) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        uuid_match = UUID_RE.search(full_text)
        if uuid_match:
            request_id = uuid_match.group(0)
        info_matches = re.findall(r"(\d{2}/\d{2}/\d{4})\s*:", full_text)
        if info_matches:
            information_date = parse_dmy(info_matches[0])
        client_id_match = re.search(r"\b(2\d{7,8})\b", full_text)
        if client_id_match:
            client_id = client_id_match.group(1)

        for idx in DETAIL_PAGE_INDICES:
            if idx >= len(pdf.pages):
                continue
            text = pdf.pages[idx].extract_text() or ""
            funds.extend(_extract_funds_from_page(text, information_date))

    if not client_id:
        raise ValueError("Client ID not found in מסלקה report")

    # Rebadge old-pension funds: page 3 funds use the 935-prefix tik (same as
    # new pension) but are actually "קרן פנסיה ותיקה". Identifiable by 12+
    # digit policy numbers (pre-reform numbering scheme).
    for f in funds:
        if f.product_category == "new_pension" and len(f.policy_number) >= 12:
            f.product_category = "old_pension"

    return MaslakaReport(
        client=ClientIdentity(full_name="", id_number=client_id),
        information_date=information_date,
        request_id=request_id,
        funds=funds,
    )
