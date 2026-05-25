"""Render an OperationForm to a Hebrew RTL PDF.

Layout matches the reference `טופס תפעול פידיון תגמולים.pdf`:
  - cover page (date, rep, client details, deal, attached-docs checklist, notes)
  - one page per פעולה (up to 6) with insurance company, product type,
    money types, tax mode, and the employers table

Implementation notes:
  - pymupdf draws text and rectangles directly (no HTML).
  - python-bidi reorders Hebrew runs for proper visual presentation.
  - Arial.ttf is used as the Hebrew font (system-installed on Windows; for
    Linux/Mac, pass FONT_PATH env var or edit FONT_FILE).
"""
from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import fitz
from bidi.algorithm import get_display

from ..models import (
    ClientPicture,
    EmployerLine,
    OperationDetail,
    OperationForm,
)

# Page geometry (A4 portrait, 72 DPI)
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 40

FONT_NAME = "Heb"
FONT_FILE = os.environ.get("SHEMESH_FONT_PATH", "C:/Windows/Fonts/arial.ttf")
FONT_BOLD_FILE = os.environ.get("SHEMESH_FONT_BOLD_PATH", "C:/Windows/Fonts/arialbd.ttf")

CHECKED = "☑"  # ☑
UNCHECKED = "☐"  # ☐

PRODUCT_LABELS = {
    "pension":       "קרן פנסיה",
    "gemel":         "קופת גמל",
    "policy":        "פוליסה",
    "study_fund":    "קרן השתלמות",
    "child_savings": "חסכון לילד",
}
PAYMENT_LABELS = {
    "credit":         "אשראי",
    "bank_transfer":  "העברה בנקאית",
    "bit":            "ביט",
    "cash":           "מזומן",
}
TAX_LABELS = {
    "full":    "מס מלא",
    "partial": "מס חלקי",
    "exempt":  "פטור ממס",
}


# ---------------------------------------------------------------------------
# Text helpers


def _rtl(text: str) -> str:
    """Bidi-reorder a string for visual RTL display."""
    if not text:
        return ""
    return get_display(text)


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _fmt_decimal(v: Decimal | None) -> str:
    if v is None:
        return ""
    return f"{v:,.2f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v):,}"


# ---------------------------------------------------------------------------
# Drawing primitives


def _ensure_fonts(page: fitz.Page) -> None:
    page.insert_font(fontname=FONT_NAME, fontfile=FONT_FILE)
    if Path(FONT_BOLD_FILE).exists():
        page.insert_font(fontname=FONT_NAME + "B", fontfile=FONT_BOLD_FILE)


def _text(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    *,
    size: int = 10,
    bold: bool = False,
    align: int = fitz.TEXT_ALIGN_RIGHT,
) -> None:
    fontname = FONT_NAME + "B" if bold and Path(FONT_BOLD_FILE).exists() else FONT_NAME
    page.insert_textbox(rect, _rtl(text), fontsize=size, fontname=fontname, align=align)


def _rect(page: fitz.Page, rect: fitz.Rect, fill: tuple | None = None) -> None:
    page.draw_rect(rect, color=(0, 0, 0), fill=fill, width=0.7)


def _checkbox(page: fitz.Page, x: float, y_baseline: float, checked: bool, size: float = 10) -> None:
    """Draw a checkbox (open square + optional X overlay).

    (x, y_baseline) is the BOTTOM-left of the box (matches the old text-glyph
    baseline so existing callsites keep working). We draw an outline always
    and an X if checked — relying on unicode ☑ glyphs is brittle because
    Arial-class fonts often render them indistinguishably from ☐.
    """
    y_top = y_baseline - size
    box = fitz.Rect(x, y_top, x + size, y_baseline)
    page.draw_rect(box, color=(0, 0, 0), width=0.6)
    if checked:
        page.draw_line(fitz.Point(x + 1.5, y_top + 1.5),
                       fitz.Point(x + size - 1.5, y_baseline - 1.5),
                       color=(0, 0, 0), width=1.2)
        page.draw_line(fitz.Point(x + size - 1.5, y_top + 1.5),
                       fitz.Point(x + 1.5, y_baseline - 1.5),
                       color=(0, 0, 0), width=1.2)


def _section_title(page: fitz.Page, y: float, text: str, size: int = 12) -> float:
    """Draw an underlined RTL section title. Returns new y cursor."""
    rect = fitz.Rect(MARGIN, y, PAGE_WIDTH - MARGIN, y + size + 4)
    _text(page, rect, text + ":", size=size, bold=True, align=fitz.TEXT_ALIGN_RIGHT)
    # Underline
    underline_y = y + size + 4
    page.draw_line(
        fitz.Point(PAGE_WIDTH - MARGIN, underline_y),
        fitz.Point(PAGE_WIDTH - MARGIN - 80, underline_y),
        color=(0, 0, 0), width=0.5,
    )
    return underline_y + 6


def _table(
    page: fitz.Page,
    x0: float,
    y0: float,
    col_widths: list[float],
    rows: list[list[str]],
    *,
    row_height: float = 22,
    header_rows: int = 1,
    header_bold: bool = True,
) -> float:
    """Draw an RTL table. Columns are listed in source/visual right-to-left
    order — `col_widths[0]` is the RIGHTMOST column on the page.

    Returns the y coordinate just below the table.
    """
    total_w = sum(col_widths)
    y = y0
    for r, row in enumerate(rows):
        is_header = r < header_rows
        # column x positions: rightmost first
        x_right = x0 + total_w
        for c, cell in enumerate(row):
            w = col_widths[c]
            x_left = x_right - w
            cell_rect = fitz.Rect(x_left, y, x_right, y + row_height)
            _rect(page, cell_rect, fill=(0.93, 0.93, 0.93) if is_header else None)
            inner = fitz.Rect(x_left + 3, y + 4, x_right - 3, y + row_height - 2)
            _text(page, inner, cell, size=9, bold=is_header and header_bold, align=fitz.TEXT_ALIGN_CENTER)
            x_right = x_left
        y += row_height
    return y


def _labeled_value(
    page: fitz.Page,
    x: float, y: float, width: float, height: float,
    label: str, value: str,
) -> None:
    """Box with label (small) on top and value below — used for cover-page fields."""
    rect = fitz.Rect(x, y, x + width, y + height)
    _rect(page, rect)
    _text(page, fitz.Rect(x, y + 2, x + width, y + 12), label, size=7, align=fitz.TEXT_ALIGN_CENTER)
    _text(page, fitz.Rect(x, y + 12, x + width, y + height - 2), value, size=10, align=fitz.TEXT_ALIGN_CENTER)


# ---------------------------------------------------------------------------
# Page renderers


def _render_cover(doc: fitz.Document, form: OperationForm, picture: Optional[ClientPicture]) -> None:
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    _ensure_fonts(page)
    cover = form.cover

    # Top: date on left, "תאריך: ____" on right
    _text(page, fitz.Rect(MARGIN, 30, 200, 50), _fmt_date(cover.form_date), size=10, align=fitz.TEXT_ALIGN_LEFT)
    _text(page, fitz.Rect(PAGE_WIDTH - MARGIN - 200, 30, PAGE_WIDTH - MARGIN, 50),
          "תאריך:________", size=10, align=fitz.TEXT_ALIGN_RIGHT)

    # Title
    _text(page, fitz.Rect(MARGIN, 65, PAGE_WIDTH - MARGIN, 95),
          "טופס תפעול", size=22, bold=True, align=fitz.TEXT_ALIGN_CENTER)
    # Underline title
    page.draw_line(fitz.Point(PAGE_WIDTH / 2 - 50, 92), fitz.Point(PAGE_WIDTH / 2 + 50, 92),
                   color=(0, 0, 0), width=1)

    # Rep name section
    y = 115
    rep_label = f"שם נציג: {cover.rep_name}"
    _text(page, fitz.Rect(MARGIN, y, PAGE_WIDTH - MARGIN, y + 18),
          rep_label, size=12, bold=True, align=fitz.TEXT_ALIGN_RIGHT)
    y += 25

    # פרטי הלקוח section title + table
    y = _section_title(page, y, "פרטי הלקוח")
    client_cols_rtl = [
        ("שם פרטי",    cover.client_first_name),
        ("שם משפחה",   cover.client_last_name),
        ("ת.ז",        cover.client_id),
        ("תאריך לידה", _fmt_date(cover.client_date_of_birth)),
        ("טלפון נייד", cover.client_phone),
        ("עיר מגורים", cover.client_city),
    ]
    inner_w = PAGE_WIDTH - 2 * MARGIN
    col_w = inner_w / len(client_cols_rtl)
    headers = [c[0] for c in client_cols_rtl]
    values =  [c[1] for c in client_cols_rtl]
    y = _table(page, MARGIN, y, [col_w] * len(client_cols_rtl),
               rows=[headers, values], row_height=22)
    y += 15

    # פרטי העסקה
    y = _section_title(page, y, "פרטי העסקה")
    deal_cols = [
        ("סכום כולל",     _fmt_decimal(cover.amount_total)),
        ("סכום שנגבה",    _fmt_decimal(cover.amount_collected)),
    ]
    pay_methods_rtl: list[tuple[str, bool]] = [
        ("אשראי",         cover.payment_method == "credit"),
        ("העברה בנקאית",  cover.payment_method == "bank_transfer"),
        ("ביט",           cover.payment_method == "bit"),
        ("מזומן",         cover.payment_method == "cash"),
    ]
    # build a row with amount cells + payment cells (each with checkbox)
    headers = [c[0] for c in deal_cols] + ["איך שולם?"] + [""] * (len(pay_methods_rtl) - 1)
    values_row = [c[1] for c in deal_cols]
    # widths: 2 amount cells + 4 payment cells share remaining
    col_n = len(deal_cols) + len(pay_methods_rtl)
    deal_col_w = inner_w / col_n

    # Header row + value/checkbox row
    header_row = [c[0] for c in deal_cols] + [m[0] for m in pay_methods_rtl]
    value_row =  [c[1] for c in deal_cols] + [""] * len(pay_methods_rtl)
    y = _table(page, MARGIN, y, col_widths=[deal_col_w] * col_n,
               rows=[header_row, value_row], row_height=22)
    # Overlay checkboxes in the payment-method cells (last len(pay_methods_rtl) cells of the value row)
    cb_row_y_baseline = y - 6  # baseline near the cell bottom
    x_right = MARGIN + col_n * deal_col_w - len(deal_cols) * deal_col_w
    # Iterate payment methods in their column positions (rightmost = index 0 in our RTL list)
    for i, (_label, checked) in enumerate(pay_methods_rtl):
        cell_x_center = x_right - (i + 0.5) * deal_col_w
        _checkbox(page, cell_x_center - 5, cb_row_y_baseline, checked, size=10)
    y += 15

    # מסמכים מצורפים — 4-column checklist
    y = _section_title(page, y, "מסמכים מצורפים")
    a = cover.attached
    docs_cols_rtl = [
        # column 1 (rightmost) = ת.ז
        ("ת.ז", [
            ("קדמי",         a.id_front),
            ("אחורי/ ספח",   a.id_back_or_sefach),
            ("אישור ניהול חשבון", a.bank_confirmation),
        ]),
        ("מס", [
            ("161-",       a.form_161),
            ("אישור מס",   a.tax_confirmation),
            ("מס מלא",     a.tax_full),
        ]),
        ("סיום/ רצף", [
            ("סיום העסקה",      a.employment_end),
            ("רצף מעסיקים",     a.retzef_employers),
            ("שחרור כספים",     a.funds_release),
        ]),
        ("איזור אישי", [
            ("יש", a.has_personal_area),
            ("אין", not a.has_personal_area),
        ]),
    ]
    # Draw header row + body
    col_w4 = inner_w / 4
    # Headers
    y = _table(page, MARGIN, y, [col_w4] * 4,
               rows=[[c[0] for c in docs_cols_rtl]],
               row_height=20)
    # Body — fixed-height block per column, each option = "label  ☑/☐"
    body_height = 22 * max(len(c[1]) for c in docs_cols_rtl)
    body_top = y
    x_right = MARGIN + 4 * col_w4
    for col_name, items in docs_cols_rtl:
        x_left = x_right - col_w4
        body_rect = fitz.Rect(x_left, body_top, x_right, body_top + body_height)
        _rect(page, body_rect)
        for i, (label, checked) in enumerate(items):
            row_y = body_top + i * 22
            # label on right inside the column, checkbox on left
            _text(page, fitz.Rect(x_left + 18, row_y + 5, x_right - 4, row_y + 19),
                  label, size=9, align=fitz.TEXT_ALIGN_RIGHT)
            _checkbox(page, x_left + 4, row_y + 16, checked, size=11)
        x_right = x_left
    y = body_top + body_height + 15

    # Two yes/no toggles
    toggles = [
        ("האם להוציא רצף מעסיקים מביטוח לאומי?", cover.pull_retzef_from_bituach_leumi),
        ("האם להוציא לצורך סגירת חוב?",           cover.pull_for_debt_closure),
    ]
    toggle_col_w = inner_w / 2
    # Each toggle gets 2 sub-columns: כן | לא
    for i, (q, val) in enumerate(toggles):
        x_left = MARGIN + (1 - i) * toggle_col_w  # rightmost first
        x_right = x_left + toggle_col_w
        # Question header
        _rect(page, fitz.Rect(x_left, y, x_right, y + 22))
        _text(page, fitz.Rect(x_left + 3, y + 5, x_right - 3, y + 19),
              q, size=9, bold=True, align=fitz.TEXT_ALIGN_CENTER)
        # Two sub-cells: כן on right, לא on left
        sub_w = toggle_col_w / 2
        for j, (label, checked) in enumerate([("כן", val), ("לא", not val)]):
            sub_x_left = x_right - (j + 1) * sub_w
            sub_rect = fitz.Rect(sub_x_left, y + 22, sub_x_left + sub_w, y + 56)
            _rect(page, sub_rect)
            _text(page, fitz.Rect(sub_x_left, y + 24, sub_x_left + sub_w, y + 36),
                  label, size=9, align=fitz.TEXT_ALIGN_CENTER)
            _checkbox(page, sub_x_left + sub_w / 2 - 5, y + 52, checked, size=11)
    y += 70

    # הערות
    y = _section_title(page, y, "הערות")
    notes_rect = fitz.Rect(MARGIN, y, PAGE_WIDTH - MARGIN, y + 80)
    _rect(page, notes_rect)
    if cover.notes:
        _text(page, fitz.Rect(MARGIN + 6, y + 6, PAGE_WIDTH - MARGIN - 6, y + 76),
              cover.notes, size=9, align=fitz.TEXT_ALIGN_RIGHT)


def _render_operation_page(
    doc: fitz.Document,
    form: OperationForm,
    op: OperationDetail | None,
    index: int,
) -> None:
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    _ensure_fonts(page)
    cover = form.cover

    # Top date
    _text(page, fitz.Rect(MARGIN, 30, 200, 50), _fmt_date(cover.form_date), size=10, align=fitz.TEXT_ALIGN_LEFT)
    _text(page, fitz.Rect(PAGE_WIDTH - MARGIN - 200, 30, PAGE_WIDTH - MARGIN, 50),
          "תאריך:________", size=10, align=fitz.TEXT_ALIGN_RIGHT)

    # Section header: פרטי פעולה / פרטי פעולה :#N
    y = 80
    title = "פרטי פעולה" if index == 0 else f"פרטי פעולה :#{index + 1}"
    y = _section_title(page, y, title)

    inner_w = PAGE_WIDTH - 2 * MARGIN

    # Top table: חברת ביטוח + 5 product type checkboxes
    company_col_w = inner_w * 0.30
    prod_col_w = (inner_w - company_col_w) / 5
    prod_types_rtl = [
        ("קרן פנסיה",    "pension"),
        ("קופת גמל",     "gemel"),
        ("פוליסה",       "policy"),
        ("קרן השתלמות",  "study_fund"),
        ("חסכון לילד",   "child_savings"),
    ]
    # Header row
    y = _table(page, MARGIN, y,
               col_widths=[company_col_w] + [prod_col_w] * 5,
               rows=[["חברת ביטוח"] + ["סוג מוצר"] + [""] * 4],
               row_height=18)
    # The next row spans: company name + product-type cells (label + checkbox)
    # Sub-header row with the 5 product labels
    y = _table(page, MARGIN, y,
               col_widths=[company_col_w] + [prod_col_w] * 5,
               rows=[[op.insurance_company if op else ""] + [label for label, _ in prod_types_rtl]],
               row_height=22, header_rows=0)
    # Checkbox row for product types (company cell stays empty)
    checkbox_row_y = y
    _rect(page, fitz.Rect(MARGIN + inner_w - company_col_w, y, MARGIN + inner_w, y + 22))
    x_right = MARGIN + inner_w - company_col_w
    for label, key in prod_types_rtl:
        x_left = x_right - prod_col_w
        _rect(page, fitz.Rect(x_left, y, x_right, y + 22))
        checked = op is not None and op.product_type == key
        _checkbox(page, x_left + prod_col_w / 2 - 5, y + 17, checked, size=11)
        x_right = x_left
    y += 22 + 10

    # Middle table: kupa_number / vintage / סוג הכספים / מיסוי
    # 3 columns: מספר קופה | וותק הקופה | סוג הכספים+מיסוי (composite)
    # The reference puts these in a single composite layout. Simplify here:
    composite_cols = [
        ("מספר קופה",  op.kupa_number if op else ""),
        ("וותק הקופה", _fmt_date(op.kupa_vintage) if op else ""),
    ]
    y = _table(page, MARGIN, y, [inner_w / 2] * 2,
               rows=[[c[0] for c in composite_cols], [c[1] for c in composite_cols]],
               row_height=22)
    y += 10

    # סוג הכספים — checkboxes for תגמולים / פיצויים
    money_types = op.money_types if op else []
    money_row = [
        ("תגמולים", "tagmulim" in money_types),
        ("פיצויים", "pitsuyim" in money_types),
    ]
    y = _table(page, MARGIN, y, [inner_w / 2] * 2,
               rows=[["סוג הכספים", ""]], row_height=18)
    # checkbox row
    x_right = MARGIN + inner_w
    for label, checked in money_row:
        x_left = x_right - inner_w / 2
        _rect(page, fitz.Rect(x_left, y, x_right, y + 22))
        # Label inside the cell, checkbox right next to it
        _text(page, fitz.Rect(x_left + 20, y + 5, x_right - 14, y + 19),
              label, size=10, align=fitz.TEXT_ALIGN_CENTER)
        _checkbox(page, x_right - 14, y + 17, checked, size=11)
        x_right = x_left
    y += 22 + 10

    # מיסוי
    tax_options_rtl = [
        ("מס מלא",   "full"),
        ("מס חלקי",  "partial"),
        ("פטור ממס", "exempt"),
    ]
    y = _table(page, MARGIN, y, [inner_w / 3] * 3,
               rows=[["מיסוי", "", ""]], row_height=18)
    x_right = MARGIN + inner_w
    for label, key in tax_options_rtl:
        x_left = x_right - inner_w / 3
        _rect(page, fitz.Rect(x_left, y, x_right, y + 22))
        _text(page, fitz.Rect(x_left + 20, y + 5, x_right - 14, y + 19),
              label, size=10, align=fitz.TEXT_ALIGN_CENTER)
        checked = op is not None and op.tax_mode == key
        _checkbox(page, x_right - 14, y + 17, checked, size=11)
        x_right = x_left
    y += 22 + 6

    if op and op.tax_mode_locked_reason:
        _text(page, fitz.Rect(MARGIN, y, PAGE_WIDTH - MARGIN, y + 12),
              f"* מיסוי ננעל אוטומטית — {op.tax_mode_locked_reason}",
              size=8, align=fitz.TEXT_ALIGN_RIGHT)
        y += 14

    # הערות (per פעולה)
    y = _section_title(page, y, "הערות")
    notes_rect = fitz.Rect(MARGIN, y, PAGE_WIDTH - MARGIN, y + 40)
    _rect(page, notes_rect)
    if op and op.notes:
        _text(page, fitz.Rect(MARGIN + 6, y + 6, PAGE_WIDTH - MARGIN - 6, y + 36),
              op.notes, size=9, align=fitz.TEXT_ALIGN_RIGHT)
    y += 50

    # מעסיקים table — 3 columns: מעסיק | תגמולים (full / amount) | פיצויים (full-tax / exempt)
    y = _section_title(page, y, "מעסיקים")
    emp_col_w = inner_w * 0.35
    tag_col_w = inner_w * 0.325
    pit_col_w = inner_w * 0.325
    # header
    y = _table(page, MARGIN, y,
               col_widths=[emp_col_w, tag_col_w, pit_col_w],
               rows=[["מעסיק", "תגמולים", "פיצויים"]],
               row_height=18)

    # Body rows — pad to 8 like the reference template
    rows: list[EmployerLine] = []
    if op:
        rows = list(op.employers)
    while len(rows) < 8:
        rows.append(EmployerLine(employer_name=""))

    for emp in rows:
        x_right = MARGIN + inner_w
        # Employer cell (rightmost)
        x_left = x_right - emp_col_w
        emp_rect = fitz.Rect(x_left, y, x_right, y + 26)
        _rect(page, emp_rect)
        _text(page, fitz.Rect(x_left + 4, y + 8, x_right - 4, y + 22),
              emp.employer_name, size=9, align=fitz.TEXT_ALIGN_CENTER)
        x_right = x_left
        # Tagmulim cell — "מלוא הסכום ☐  על סך ____  ☐"
        x_left = x_right - tag_col_w
        tag_rect = fitz.Rect(x_left, y, x_right, y + 26)
        _rect(page, tag_rect)
        full_label = "מלוא הסכום"
        _text(page, fitz.Rect(x_left + 18, y + 5, x_left + tag_col_w / 2 - 4, y + 19),
              full_label, size=8, align=fitz.TEXT_ALIGN_CENTER)
        _checkbox(page, x_left + 6, y + 17, emp.tagmulim_full, size=10)
        # Amount sub-cell
        amount_text = f"על סך {_fmt_decimal(emp.tagmulim_amount)}" if emp.tagmulim_amount else "על סך _______"
        _text(page, fitz.Rect(x_left + tag_col_w / 2 + 14, y + 5, x_right - 4, y + 19),
              amount_text, size=8, align=fitz.TEXT_ALIGN_CENTER)
        amt_checked = bool(emp.tagmulim_amount and not emp.tagmulim_full)
        _checkbox(page, x_left + tag_col_w / 2 + 2, y + 17, amt_checked, size=10)
        x_right = x_left
        # Pitsuyim cell — "מס מלא ☐  פטור מס ☐"
        x_left = x_right - pit_col_w
        pit_rect = fitz.Rect(x_left, y, x_right, y + 26)
        _rect(page, pit_rect)
        _text(page, fitz.Rect(x_left + 18, y + 5, x_left + pit_col_w / 2 - 4, y + 19),
              "מס מלא", size=8, align=fitz.TEXT_ALIGN_CENTER)
        _checkbox(page, x_left + 6, y + 17, emp.pitsuyim_full_tax, size=10)
        _text(page, fitz.Rect(x_left + pit_col_w / 2 + 14, y + 5, x_right - 4, y + 19),
              "פטור מס", size=8, align=fitz.TEXT_ALIGN_CENTER)
        _checkbox(page, x_left + pit_col_w / 2 + 2, y + 17, emp.pitsuyim_tax_exempt, size=10)

        y += 26

    y += 10
    y = _section_title(page, y, "הערות")
    final_notes = fitz.Rect(MARGIN, y, PAGE_WIDTH - MARGIN, y + 40)
    _rect(page, final_notes)


# ---------------------------------------------------------------------------
# Public API


def render_form_to_pdf(
    form: OperationForm,
    picture: Optional[ClientPicture],
    out_path: Path | str,
) -> Path:
    """Render the form to a PDF file on disk. Returns the path written."""
    out_path = Path(out_path)
    out_path.write_bytes(render_form_to_bytes(form, picture))
    return out_path


def render_form_to_bytes(form: OperationForm, picture: Optional[ClientPicture]) -> bytes:
    doc = fitz.open()
    _render_cover(doc, form, picture)
    # Render configured operations, then pad blank operation pages up to max.
    ops = list(form.operations)
    for i in range(form.max_operations):
        op = ops[i] if i < len(ops) else None
        _render_operation_page(doc, form, op, i)
    out = doc.tobytes()
    doc.close()
    return out
