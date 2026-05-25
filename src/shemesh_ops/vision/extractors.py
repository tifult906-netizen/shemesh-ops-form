"""High-level extractors built on top of any VisionExtractor backend.

Each function takes either raw image bytes or a PDF path + page indices,
calls the vision extractor with a structured prompt, and returns Pydantic
models (or fills missing fields on existing models in place).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import (
    BankAccount,
    BLEmployerDetail,
    BLEmploymentHistory,
    IDCard,
    MaslakaReport,
    PitsuyimReport,
    TagmulimReport,
)
from .base import VisionExtractor, render_pdf_pages


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                from datetime import datetime
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None


# ---------------------------------------------------------------------------
# ID card

ID_CARD_INSTRUCTION = """You are reading the front and back of an Israeli biometric ID card (תעודת זהות).
Extract these fields, using Hebrew text exactly as printed:
  full_name (שם מלא — first + last),
  first_name (השם הפרטי),
  last_name (שם המשפחה),
  id_number (מספר זהות — 9 digits including the check digit, with leading zero if any),
  date_of_birth (תאריך לידה, ISO format YYYY-MM-DD),
  issue_date (תאריך הנפקה, ISO),
  expiry_date (בתוקף עד, ISO),
  father_name (שם האב),
  mother_name (שם האם),
  grandfather_name (שם הסב),
  place_of_birth (מקום לידה),
  card_number (מספר הכרטיס, printed near the bottom of the back),
  sex (מין),
  citizenship (מעמד / אזרחות).
Use null for any field that is not visible. Do not invent values.
"""


def extract_id_card(
    front_image: bytes,
    back_image: bytes,
    vision: VisionExtractor,
) -> IDCard:
    raw = vision.extract(
        images=[front_image, back_image],
        instruction=ID_CARD_INSTRUCTION,
        task_name="id_card",
    )
    return IDCard(
        full_name=raw.get("full_name") or f"{raw.get('first_name','')} {raw.get('last_name','')}".strip(),
        first_name=raw.get("first_name"),
        last_name=raw.get("last_name"),
        id_number=raw["id_number"],
        date_of_birth=_parse_date(raw.get("date_of_birth")),
        issue_date=_parse_date(raw.get("issue_date")),
        expiry_date=_parse_date(raw.get("expiry_date")),
        father_name=raw.get("father_name"),
        mother_name=raw.get("mother_name"),
        grandfather_name=raw.get("grandfather_name"),
        place_of_birth=raw.get("place_of_birth"),
        card_number=raw.get("card_number"),
        sex=raw.get("sex"),
        citizenship=raw.get("citizenship"),
    )


# ---------------------------------------------------------------------------
# Bank-confirmation Hebrew labels

BANK_INSTRUCTION = """You are reading an Israeli bank account confirmation (אישור ניהול חשבון).
Extract these two Hebrew fields exactly as printed:
  holder_name (שם בעל החשבון),
  address (כתובת החשבון).
Use null if a field is not present.
"""


def fill_bank_labels(bank: BankAccount, pdf_path: Path | str, vision: VisionExtractor) -> None:
    pages = render_pdf_pages(pdf_path, [0])
    raw = vision.extract(images=pages, instruction=BANK_INSTRUCTION, task_name="bank_labels")
    if raw.get("holder_name"):
        bank.holder_name = raw["holder_name"]
    if raw.get("address"):
        bank.address = raw["address"]


# ---------------------------------------------------------------------------
# Tagmulim per-fund labels

TAGMULIM_INSTRUCTION_TEMPLATE = """You are reading a Hebrew pension-clearing-house report (דוח יתרות תגמולים).
The funds table has {n} data rows. For each row in order (top to bottom),
return kupa_name (שם קופה) and member_status (מעמד עמית — "שכיר" / "עצמאי" / "מנהלת" etc.).
Return JSON: {{"items": [{{"kupa_name": "...", "member_status": "..."}}, ...]}}.
"""


def fill_tagmulim_labels(report: TagmulimReport, pdf_path: Path | str, vision: VisionExtractor) -> None:
    pages = render_pdf_pages(pdf_path, [0])
    instruction = TAGMULIM_INSTRUCTION_TEMPLATE.format(n=len(report.funds))
    raw = vision.extract(images=pages, instruction=instruction, task_name="tagmulim_labels")
    items = raw.get("items", [])
    for fund, item in zip(report.funds, items):
        if item.get("kupa_name"):
            fund.kupa_name = item["kupa_name"]
        if item.get("member_status"):
            fund.member_status = item["member_status"]


# ---------------------------------------------------------------------------
# Pitsuyim per-row labels

PITSUYIM_INSTRUCTION_TEMPLATE = """You are reading a Hebrew pension-clearing-house report (דוח יתרות פיצויים).
The rows table has {n} rows. For each row in order (top to bottom), return
kupa_name (שם קופה) and employer_name (שם מעסיק — use "מעסיק עצמאי" for self-employed,
or the client's own name for the row representing the client themselves).
Return JSON: {{"items": [{{"kupa_name": "...", "employer_name": "..."}}, ...]}}.
"""


def fill_pitsuyim_labels(report: PitsuyimReport, pdf_path: Path | str, vision: VisionExtractor) -> None:
    pages = render_pdf_pages(pdf_path, [0])
    instruction = PITSUYIM_INSTRUCTION_TEMPLATE.format(n=len(report.rows))
    raw = vision.extract(images=pages, instruction=instruction, task_name="pitsuyim_labels")
    items = raw.get("items", [])
    for row, item in zip(report.rows, items):
        if item.get("kupa_name"):
            row.kupa_name = item["kupa_name"]
        if item.get("employer_name"):
            row.employer_name = item["employer_name"]


# ---------------------------------------------------------------------------
# Maslaka per-fund labels

MASLAKA_INSTRUCTION = """You are reading per-fund detail pages from a Hebrew pension-clearing-house
report (דוח מסלקה). There are {n} funds across pages 3-6 in source order
(each page may show 1, 2, or 3 funds in side-by-side columns; columns read
right-to-left in the source).

For each fund in source order, return:
  management_company (שם חברה מנהלת, e.g. "חברה דוגמה ב"),
  status (סטטוס — "פעיל" / "לא פעיל"),
  product_type_label (סוג מוצר פנסיוני, e.g. "פנסיה חדשה מקיפה" or "קרן השתלמות").

Return JSON: {{"items": [{{...}} x {n}]}}.
"""


def fill_maslaka_labels(report: MaslakaReport, pdf_path: Path | str, vision: VisionExtractor) -> None:
    pages = render_pdf_pages(pdf_path, [2, 3, 4, 5])  # pages 3,4,5,6
    instruction = MASLAKA_INSTRUCTION.format(n=len(report.funds))
    raw = vision.extract(images=pages, instruction=instruction, task_name="maslaka_labels")
    items = raw.get("items", [])
    for fund, item in zip(report.funds, items):
        if item.get("management_company"):
            fund.management_company = item["management_company"]
        if item.get("status"):
            fund.status = item["status"]
        if item.get("product_type_label"):
            fund.product_type_label = item["product_type_label"]


# ---------------------------------------------------------------------------
# BL employment history labels (periods + employer details)

BL_PERIODS_INSTRUCTION = """You are reading the periods table of an Israeli National Insurance
employment-history confirmation (אישור תקופות ביטוח ומעסיקים). The table
has {n} rows. For each row in order, return:
  occupation (עיסוק — "עובד" / "חבר קיבוץ" / "עצמאי" / "עצמאי לא עונה להגדרה"),
  employer_label (פרטי המדווח — the employer/קיבוץ name; empty string for self-employed).

Return JSON: {{"items": [{{...}} x {n}]}}.
"""


BL_EMPLOYERS_INSTRUCTION = """The same document has an employer-details cross-reference table with
{n} unique employers. For each employer (in the order they appear), return:
  tik_maasik (תיק המעסיק — the 11-digit BL file number),
  employer_name (שם המעסיק),
  address (כתובת — full address as printed).

Return JSON: {{"items": [{{...}} x {n}]}}.
"""


def fill_bl_labels(history: BLEmploymentHistory, pdf_path: Path | str, vision: VisionExtractor) -> None:
    pages = render_pdf_pages(pdf_path, list(range(_count_pages(pdf_path))))

    periods_instr = BL_PERIODS_INSTRUCTION.format(n=len(history.periods))
    periods_raw = vision.extract(images=pages, instruction=periods_instr, task_name="bl_periods_labels")
    periods_items = periods_raw.get("items", [])
    for period, item in zip(history.periods, periods_items):
        if item.get("occupation"):
            period.occupation = item["occupation"]
        if item.get("employer_label") is not None:
            period.employer_label = item["employer_label"]

    emp_instr = BL_EMPLOYERS_INSTRUCTION.format(n=len(history.employer_details))
    emp_raw = vision.extract(images=pages, instruction=emp_instr, task_name="bl_employer_details_labels")
    emp_items = emp_raw.get("items", [])
    # The mock returns tuples (tik, name, address); the real backend returns dicts.
    new_details: list[BLEmployerDetail] = []
    by_tik = {e.tik_maasik: e for e in history.employer_details}
    for item in emp_items:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            tik, name, address = item[0], item[1], item[2]
        else:
            tik = item.get("tik_maasik")
            name = item.get("employer_name")
            address = item.get("address")
        if not tik:
            continue
        existing = by_tik.get(tik)
        if existing:
            existing.employer_name = name or existing.employer_name
            existing.address = address or existing.address
            new_details.append(existing)
        else:
            new_details.append(BLEmployerDetail(tik_maasik=tik, employer_name=name or "", address=address))
    if new_details:
        history.employer_details = new_details


def _count_pages(pdf_path: Path | str) -> int:
    import fitz
    with fitz.open(str(pdf_path)) as doc:
        return len(doc)
