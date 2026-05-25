"""Parser for 'אישור ניהול חשבון' (bank account confirmation PDF).

The Hebrew text layer uses custom CID-mapped fonts, so Hebrew labels (holder
name, address) do not extract cleanly via pdfplumber. Numeric/Latin fields
(IDs, IBAN, dates, account numbers) extract perfectly and are pulled via regex.

Hebrew fields are left as None here — they are filled in by the vision pass
downstream (see step 4 in UNDERSTANDING.md §10).
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models import BankAccount
from ._pdf_utils import extract_raw_text, parse_dmy

ID_RE = re.compile(r"\b(\d{9})\b")
IBAN_RE = re.compile(r"IL\d{2}\d{4}\d{6}\d{8,}")
ISSUE_DATE_RE = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s+bankhapoalim", re.MULTILINE)
OPENED_DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})")
ACCOUNT_LINE_RE = re.compile(r"^\s*(\d{1,3})\s+(\d{3,4})\s+(\d{4,8})\s", re.MULTILINE)


def parse_bank_confirmation(pdf_path: Path | str) -> BankAccount:
    text = extract_raw_text(pdf_path)

    id_match = ID_RE.search(text)
    if not id_match:
        raise ValueError("ID number not found in bank confirmation")
    id_number = id_match.group(1)

    iban_match = IBAN_RE.search(text)
    iban = iban_match.group(0) if iban_match else None

    issue_match = ISSUE_DATE_RE.search(text)
    issue_date = parse_dmy(issue_match.group(1)) if issue_match else None

    bank_code = branch = account_number = ""
    acct_match = ACCOUNT_LINE_RE.search(text)
    if acct_match:
        bank_code, branch, account_number = acct_match.group(1), acct_match.group(2), acct_match.group(3)
    else:
        for m in re.finditer(r"\b(\d{1,3})\s+(\d{3,4})\s+(\d{4,8})\b", text):
            if len(m.group(3)) >= 5:
                bank_code, branch, account_number = m.group(1), m.group(2), m.group(3)
                break

    return BankAccount(
        holder_name="",  # filled by vision pass
        id_number=id_number,
        bank_code=bank_code,
        bank_name=_bank_name_from_code(bank_code),
        branch=branch,
        account_number=account_number,
        iban=iban,
        address=None,  # filled by vision pass
        issue_date=issue_date,
    )


_BANK_NAMES = {
    "10": "לאומי",
    "11": "דיסקונט",
    "12": "הפועלים",
    "13": "הבינלאומי",
    "17": "מרכנתיל",
    "20": "מזרחי טפחות",
    "31": "הבינלאומי",
    "46": "מסד",
    "52": "פאגי",
    "54": "ירושלים",
    "73": "וואן זירו",
}


def _bank_name_from_code(code: str) -> str | None:
    return _BANK_NAMES.get(code)
