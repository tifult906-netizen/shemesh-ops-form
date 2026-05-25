"""Parser for 'אישור תקופות ביטוח ומעסיקים' (National Insurance employment history).

3-page PDF. Page 1 + start of page 2 list employment periods. Page 2 also has
the employer-details cross-reference table (tik_maasik → name + address).

Hebrew text in this PDF is letter-reversed within each token (a quirk of the
BL issuing tool, same as מסלקה pages 1-8). Dates, months, and 11-digit
tik_maasik numbers extract cleanly. Hebrew names/addresses are deferred to
the vision pass.

Per period-row, extracted text order is right-to-left of source visual:
    [employer] [occupation] [months] [date_to] [date_from]
so the date_from is the LAST date on the line. For open-ended (still-current)
periods only date_from is present.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pdfplumber

from ..models import (
    BLEmployerDetail,
    BLEmploymentHistory,
    ClientIdentity,
    EmploymentPeriod,
)
from ._pdf_utils import parse_dmy

DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
TIK_MAASIK_RE = re.compile(r"\b(9\d{10})\b")  # 11-digit, BL employer-file format
MONTHS_RE = re.compile(r"\s(\d{1,3})\s")
CLIENT_ID_RE = re.compile(r"(\d{7,8})-(\d)")


def _normalize_client_id(raw: str) -> str:
    """BL writes client ID as e.g. '2974259-0' (= 0-9524792 reversed-digit)
    which is the client's true ID '29742590' with a check-digit dash."""
    raw = raw.replace("-", "").replace(" ", "")
    if len(raw) == 8:
        raw = "0" + raw
    return raw


def parse_bl_history(pdf_path: Path | str) -> BLEmploymentHistory:
    periods: list[EmploymentPeriod] = []
    employer_details: list[BLEmployerDetail] = []
    client_id: str | None = None
    issue_date: date | None = None

    seen_tiks: set[str] = set()

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.split("\n")

            for line in lines:
                if client_id is None:
                    cid = CLIENT_ID_RE.search(line)
                    if cid:
                        client_id = _normalize_client_id(cid.group(0))

                tik_match = TIK_MAASIK_RE.search(line)
                if tik_match:
                    tik = tik_match.group(1)
                    if tik not in seen_tiks:
                        employer_details.append(
                            BLEmployerDetail(
                                tik_maasik=tik,
                                employer_name="",  # vision pass
                                address=None,  # vision pass
                            )
                        )
                        seen_tiks.add(tik)
                    continue  # employer-detail line; not a period line

                dates_in_line = DATE_RE.findall(line)
                if not dates_in_line:
                    continue

                # Period rows have 1 or 2 dates. Header/footer noise may also
                # have dates — filter by requiring a months integer before the
                # date(s).
                date_from = parse_dmy(dates_in_line[-1])
                date_to = parse_dmy(dates_in_line[-2]) if len(dates_in_line) >= 2 else None

                # Find the months integer: it precedes the date(s) in the
                # extracted line (right-to-left).
                pre_date_part = line.rsplit(dates_in_line[-2] if date_to else dates_in_line[-1], 1)[0]
                if date_to:
                    pre_date_part = pre_date_part.rsplit(dates_in_line[-1], 1)[0]
                months_matches = re.findall(r"\b(\d{1,3})\b", pre_date_part)
                months = int(months_matches[-1]) if months_matches else None

                # Heuristic: ignore header/legend lines that have only a date.
                if months is None and date_to is None:
                    continue

                periods.append(
                    EmploymentPeriod(
                        date_from=date_from,
                        date_to=date_to,
                        months=months,
                        occupation="",  # vision pass
                        employer_label="",  # vision pass
                        note=None,
                    )
                )

    if not client_id:
        raise ValueError("Client ID not found in BL employment history")

    return BLEmploymentHistory(
        client=ClientIdentity(full_name="", id_number=client_id),
        issue_date=issue_date,
        periods=periods,
        employer_details=employer_details,
    )
