"""Render an OperationForm to a Hebrew RTL PDF.

Stack: reportlab.canvas for PDF drawing + python-bidi for RTL reordering.
No pymupdf dependency (its native DLL is blocked by Windows Defender
Application Control on some managed machines).

Coordinate system note: reportlab uses bottom-left origin (Y goes up),
while a natural reading layout treats top-left as origin (Y goes down).
We define `_y(top_y)` to convert from top-down to bottom-up consistently
throughout the renderer.
"""
from __future__ import annotations

import io
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from bidi.algorithm import get_display
from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from ..models import (
    ClientPicture,
    EmployerLine,
    OperationDetail,
    OperationForm,
)

PAGE_WIDTH, PAGE_HEIGHT = A4
PAGE_WIDTH, PAGE_HEIGHT = int(PAGE_WIDTH), int(PAGE_HEIGHT)
MARGIN = 40

FONT_NAME = "Heb"
FONT_BOLD_NAME = "HebBold"
FONT_FILE = os.environ.get("SHEMESH_FONT_PATH", "C:/Windows/Fonts/arial.ttf")
FONT_BOLD_FILE = os.environ.get("SHEMESH_FONT_BOLD_PATH", "C:/Windows/Fonts/arialbd.ttf")

HEADER_FILL = Color(0.93, 0.93, 0.93)

_fonts_registered = False


def _register_fonts_once() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_FILE))
    except Exception:
        # Fall back to default font; Hebrew will render as boxes but
        # the PDF will still produce.
        pass
    if Path(FONT_BOLD_FILE).exists():
        try:
            pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, FONT_BOLD_FILE))
        except Exception:
            pass
    _fonts_registered = True


# ---------------------------------------------------------------------------
# Text helpers

def _rtl(text: str) -> str:
    if not text:
        return ""
    return get_display(text)


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _fmt_decimal(v: Decimal | None) -> str:
    if v is None:
        return ""
    return f"{v:,.2f}".rstrip("0").rstrip(".") if v != int(v) else f"{int(v):,}"


def _y(top_y: float) -> float:
    """Convert top-down y to bottom-up reportlab y."""
    return PAGE_HEIGHT - top_y


# ---------------------------------------------------------------------------
# Drawing primitives

def _font(bold: bool) -> str:
    if bold and FONT_BOLD_NAME in pdfmetrics.getRegisteredFontNames():
        return FONT_BOLD_NAME
    return FONT_NAME


def _text(
    c: rl_canvas.Canvas,
    x: float, top_y: float, width: float, height: float,
    text: str,
    *,
    size: int = 10,
    bold: bool = False,
    align: str = "right",  # 'left' | 'center' | 'right'
) -> None:
    """Draw text inside the box (x, top_y, x+width, top_y+height)."""
    rtl_text = _rtl(text)
    font = _font(bold)
    c.setFont(font, size)
    # Baseline ~ center vertically. ReportLab text baseline is at the y
    # coordinate; we want the middle of the box to roughly line up.
    bottom_y = _y(top_y + height)
    text_baseline_y = bottom_y + (height - size) / 2 + size * 0.18  # approx vertical center
    if align == "left":
        c.drawString(x + 2, text_baseline_y, rtl_text)
    elif align == "center":
        c.drawCentredString(x + width / 2, text_baseline_y, rtl_text)
    else:  # right
        c.drawRightString(x + width - 2, text_baseline_y, rtl_text)


def _rect(
    c: rl_canvas.Canvas,
    x: float, top_y: float, width: float, height: float,
    fill: Optional[Color] = None,
) -> None:
    c.setStrokeColor(black)
    c.setLineWidth(0.7)
    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, _y(top_y + height), width, height, stroke=1, fill=1)
        c.setFillColor(black)
    else:
        c.rect(x, _y(top_y + height), width, height, stroke=1, fill=0)


def _line(c: rl_canvas.Canvas, x1: float, top_y1: float, x2: float, top_y2: float, width: float = 0.5) -> None:
    c.setStrokeColor(black)
    c.setLineWidth(width)
    c.line(x1, _y(top_y1), x2, _y(top_y2))


def _checkbox(
    c: rl_canvas.Canvas,
    x: float, top_y_baseline: float,
    checked: bool,
    size: float = 10,
) -> None:
    """Draw an open square with an optional X overlay. (x, top_y_baseline) is
    the BOTTOM-LEFT of the box in top-down coordinates (matches the original
    pymupdf API the rest of the renderer was written against)."""
    top = top_y_baseline - size
    c.setStrokeColor(black)
    c.setLineWidth(0.6)
    c.rect(x, _y(top + size), size, size, stroke=1, fill=0)
    if checked:
        c.setLineWidth(1.2)
        c.line(x + 1.5, _y(top + 1.5), x + size - 1.5, _y(top + size - 1.5))
        c.line(x + size - 1.5, _y(top + 1.5), x + 1.5, _y(top + size - 1.5))


def _section_title(c: rl_canvas.Canvas, top_y: float, text: str, size: int = 12) -> float:
    """Draw a right-aligned underlined section title. Returns the y cursor
    just below the title (in top-down coordinates)."""
    _text(c, MARGIN, top_y, PAGE_WIDTH - 2 * MARGIN, size + 4, text + ":",
          size=size, bold=True, align="right")
    underline_y = top_y + size + 4
    _line(c, PAGE_WIDTH - MARGIN - 80, underline_y, PAGE_WIDTH - MARGIN, underline_y, width=0.5)
    return underline_y + 6


def _table(
    c: rl_canvas.Canvas,
    x0: float, top_y0: float,
    col_widths: list[float],
    rows: list[list[str]],
    *,
    row_height: float = 22,
    header_rows: int = 1,
    header_bold: bool = True,
) -> float:
    """Draw an RTL table. Columns are listed in source/visual right-to-left
    order. Returns the y coordinate just below the table (top-down)."""
    total_w = sum(col_widths)
    y = top_y0
    for r, row in enumerate(rows):
        is_header = r < header_rows
        x_right = x0 + total_w
        for col_idx, cell in enumerate(row):
            w = col_widths[col_idx]
            x_left = x_right - w
            fill = HEADER_FILL if is_header else None
            _rect(c, x_left, y, w, row_height, fill=fill)
            _text(c, x_left + 3, y + 2, w - 6, row_height - 4,
                  cell, size=9, bold=is_header and header_bold, align="center")
            x_right = x_left
        y += row_height
    return y


# ---------------------------------------------------------------------------
# Page renderers

PRODUCT_TYPES_RTL = [
    ("קרן פנסיה",    "pension"),
    ("קופת גמל",     "gemel"),
    ("פוליסה",       "policy"),
    ("קרן השתלמות",  "study_fund"),
    ("חסכון לילד",   "child_savings"),
]
TAX_OPTIONS_RTL = [
    ("מס מלא",   "full"),
    ("מס חלקי",  "partial"),
    ("פטור ממס", "exempt"),
]


def _render_cover(c: rl_canvas.Canvas, form: OperationForm) -> None:
    cover = form.cover

    # Top: date on left, placeholder on right
    _text(c, MARGIN, 30, 200, 16, _fmt_date(cover.form_date), size=10, align="left")
    _text(c, PAGE_WIDTH - MARGIN - 200, 30, 200, 16, "תאריך:________", size=10, align="right")

    # Title
    _text(c, MARGIN, 65, PAGE_WIDTH - 2 * MARGIN, 28,
          "טופס תפעול", size=22, bold=True, align="center")
    _line(c, PAGE_WIDTH / 2 - 50, 95, PAGE_WIDTH / 2 + 50, 95, width=1)

    y = 115
    rep_label = f"שם נציג: {cover.rep_name}"
    _text(c, MARGIN, y, PAGE_WIDTH - 2 * MARGIN, 18, rep_label, size=12, bold=True, align="right")
    y += 25

    # פרטי הלקוח
    y = _section_title(c, y, "פרטי הלקוח")
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
    headers = [v[0] for v in client_cols_rtl]
    values = [v[1] for v in client_cols_rtl]
    y = _table(c, MARGIN, y, [col_w] * len(client_cols_rtl),
               rows=[headers, values], row_height=22)
    y += 15

    # פרטי העסקה
    y = _section_title(c, y, "פרטי העסקה")
    deal_cols = [
        ("סכום כולל",   _fmt_decimal(cover.amount_total)),
        ("סכום שנגבה",  _fmt_decimal(cover.amount_collected)),
    ]
    pay_methods_rtl = [
        ("אשראי",         cover.payment_method == "credit"),
        ("העברה בנקאית",  cover.payment_method == "bank_transfer"),
        ("ביט",           cover.payment_method == "bit"),
        ("מזומן",         cover.payment_method == "cash"),
    ]
    col_n = len(deal_cols) + len(pay_methods_rtl)
    deal_col_w = inner_w / col_n
    header_row = [v[0] for v in deal_cols] + [m[0] for m in pay_methods_rtl]
    value_row = [v[1] for v in deal_cols] + [""] * len(pay_methods_rtl)
    y = _table(c, MARGIN, y, col_widths=[deal_col_w] * col_n,
               rows=[header_row, value_row], row_height=22)
    # Overlay checkboxes in the payment-method cells
    cb_y_baseline = y - 6
    x_right = MARGIN + col_n * deal_col_w - len(deal_cols) * deal_col_w
    for i, (_label, checked) in enumerate(pay_methods_rtl):
        cx_center = x_right - (i + 0.5) * deal_col_w
        _checkbox(c, cx_center - 5, cb_y_baseline, checked, size=10)
    y += 15

    # מסמכים מצורפים
    y = _section_title(c, y, "מסמכים מצורפים")
    a = cover.attached
    docs_cols_rtl = [
        ("ת.ז", [
            ("קדמי",                a.id_front),
            ("אחורי/ ספח",          a.id_back_or_sefach),
            ("אישור ניהול חשבון",   a.bank_confirmation),
        ]),
        ("מס", [
            ("161-",       a.form_161),
            ("אישור מס",   a.tax_confirmation),
            ("מס מלא",     a.tax_full),
        ]),
        ("סיום/ רצף", [
            ("סיום העסקה",   a.employment_end),
            ("רצף מעסיקים",  a.retzef_employers),
            ("שחרור כספים",  a.funds_release),
        ]),
        ("איזור אישי", [
            ("יש",  a.has_personal_area),
            ("אין", not a.has_personal_area),
        ]),
    ]
    col_w4 = inner_w / 4
    y = _table(c, MARGIN, y, [col_w4] * 4,
               rows=[[v[0] for v in docs_cols_rtl]], row_height=20)
    body_height = 22 * max(len(c[1]) for c in docs_cols_rtl)
    body_top = y
    x_right = MARGIN + 4 * col_w4
    for col_name, items in docs_cols_rtl:
        x_left = x_right - col_w4
        _rect(c, x_left, body_top, col_w4, body_height)
        for i, (label, checked) in enumerate(items):
            row_y = body_top + i * 22
            _text(c, x_left + 18, row_y + 5, col_w4 - 22, 14,
                  label, size=9, align="right")
            _checkbox(c, x_left + 4, row_y + 16, checked, size=11)
        x_right = x_left
    y = body_top + body_height + 15

    # Yes/no toggles
    toggles = [
        ("האם להוציא רצף מעסיקים מביטוח לאומי?", cover.pull_retzef_from_bituach_leumi),
        ("האם להוציא לצורך סגירת חוב?",           cover.pull_for_debt_closure),
    ]
    toggle_col_w = inner_w / 2
    for i, (q, val) in enumerate(toggles):
        x_left = MARGIN + (1 - i) * toggle_col_w
        x_right = x_left + toggle_col_w
        _rect(c, x_left, y, toggle_col_w, 22)
        _text(c, x_left + 3, y + 5, toggle_col_w - 6, 14, q, size=9, bold=True, align="center")
        sub_w = toggle_col_w / 2
        for j, (label, checked) in enumerate([("כן", val), ("לא", not val)]):
            sub_x_left = x_right - (j + 1) * sub_w
            _rect(c, sub_x_left, y + 22, sub_w, 34)
            _text(c, sub_x_left, y + 24, sub_w, 12, label, size=9, align="center")
            _checkbox(c, sub_x_left + sub_w / 2 - 5, y + 52, checked, size=11)
    y += 70

    # הערות
    y = _section_title(c, y, "הערות")
    _rect(c, MARGIN, y, PAGE_WIDTH - 2 * MARGIN, 80)
    if cover.notes:
        _text(c, MARGIN + 6, y + 6, PAGE_WIDTH - 2 * MARGIN - 12, 70,
              cover.notes, size=9, align="right")


def _render_operation_page(c: rl_canvas.Canvas, form: OperationForm, op: OperationDetail | None, index: int) -> None:
    cover = form.cover
    inner_w = PAGE_WIDTH - 2 * MARGIN

    # Top date
    _text(c, MARGIN, 30, 200, 16, _fmt_date(cover.form_date), size=10, align="left")
    _text(c, PAGE_WIDTH - MARGIN - 200, 30, 200, 16, "תאריך:________", size=10, align="right")

    y = 80
    title = "פרטי פעולה" if index == 0 else f"פרטי פעולה :#{index + 1}"
    y = _section_title(c, y, title)

    # Insurance company + product types
    company_col_w = inner_w * 0.30
    prod_col_w = (inner_w - company_col_w) / 5
    y = _table(c, MARGIN, y,
               col_widths=[company_col_w] + [prod_col_w] * 5,
               rows=[["חברת ביטוח"] + ["סוג מוצר"] + [""] * 4],
               row_height=18)
    y = _table(c, MARGIN, y,
               col_widths=[company_col_w] + [prod_col_w] * 5,
               rows=[[op.insurance_company if op else ""] + [label for label, _ in PRODUCT_TYPES_RTL]],
               row_height=22, header_rows=0)
    # Checkbox row
    _rect(c, MARGIN + inner_w - company_col_w, y, company_col_w, 22)
    x_right = MARGIN + inner_w - company_col_w
    for label, key in PRODUCT_TYPES_RTL:
        x_left = x_right - prod_col_w
        _rect(c, x_left, y, prod_col_w, 22)
        checked = op is not None and op.product_type == key
        _checkbox(c, x_left + prod_col_w / 2 - 5, y + 17, checked, size=11)
        x_right = x_left
    y += 22 + 10

    # kupa info
    composite_cols = [
        ("מספר קופה",  op.kupa_number if op else ""),
        ("וותק הקופה", _fmt_date(op.kupa_vintage) if op else ""),
    ]
    y = _table(c, MARGIN, y, [inner_w / 2] * 2,
               rows=[[v[0] for v in composite_cols], [v[1] for v in composite_cols]],
               row_height=22)
    y += 10

    # סוג הכספים
    money_types = op.money_types if op else []
    money_row = [("תגמולים", "tagmulim" in money_types), ("פיצויים", "pitsuyim" in money_types)]
    y = _table(c, MARGIN, y, [inner_w / 2] * 2,
               rows=[["סוג הכספים", ""]], row_height=18)
    x_right = MARGIN + inner_w
    for label, checked in money_row:
        x_left = x_right - inner_w / 2
        _rect(c, x_left, y, inner_w / 2, 22)
        _text(c, x_left + 20, y + 5, inner_w / 2 - 34, 14, label, size=10, align="center")
        _checkbox(c, x_right - 14, y + 17, checked, size=11)
        x_right = x_left
    y += 22 + 10

    # מיסוי
    y = _table(c, MARGIN, y, [inner_w / 3] * 3, rows=[["מיסוי", "", ""]], row_height=18)
    x_right = MARGIN + inner_w
    for label, key in TAX_OPTIONS_RTL:
        x_left = x_right - inner_w / 3
        _rect(c, x_left, y, inner_w / 3, 22)
        _text(c, x_left + 20, y + 5, inner_w / 3 - 34, 14, label, size=10, align="center")
        checked = op is not None and op.tax_mode == key
        _checkbox(c, x_right - 14, y + 17, checked, size=11)
        x_right = x_left
    y += 22 + 6

    if op and op.tax_mode_locked_reason:
        _text(c, MARGIN, y, inner_w, 12,
              f"* מיסוי ננעל אוטומטית - {op.tax_mode_locked_reason}",
              size=8, align="right")
        y += 14

    # הערות (per פעולה)
    y = _section_title(c, y, "הערות")
    _rect(c, MARGIN, y, inner_w, 40)
    if op and op.notes:
        _text(c, MARGIN + 6, y + 6, inner_w - 12, 30, op.notes, size=9, align="right")
    y += 50

    # מעסיקים
    y = _section_title(c, y, "מעסיקים")
    emp_col_w = inner_w * 0.35
    tag_col_w = inner_w * 0.325
    pit_col_w = inner_w * 0.325
    y = _table(c, MARGIN, y,
               col_widths=[emp_col_w, tag_col_w, pit_col_w],
               rows=[["מעסיק", "תגמולים", "פיצויים"]],
               row_height=18)

    rows: list[EmployerLine] = list(op.employers) if op else []
    while len(rows) < 8:
        rows.append(EmployerLine(employer_name=""))

    op_tax_default = op.tax_mode if op else None
    for emp in rows:
        # Resolve the effective tax mode for this employer: per-employer
        # override > operation default > legacy booleans.
        eff_tax = emp.tax_mode or op_tax_default
        if eff_tax is None:
            if emp.pitsuyim_full_tax:
                eff_tax = "full"
            elif emp.pitsuyim_tax_exempt:
                eff_tax = "exempt"

        x_right = MARGIN + inner_w
        x_left = x_right - emp_col_w
        _rect(c, x_left, y, emp_col_w, 26)
        _text(c, x_left + 4, y + 8, emp_col_w - 8, 14, emp.employer_name, size=9, align="center")
        x_right = x_left
        x_left = x_right - tag_col_w
        _rect(c, x_left, y, tag_col_w, 26)
        _text(c, x_left + 18, y + 5, tag_col_w / 2 - 22, 14, "מלוא הסכום", size=8, align="center")
        _checkbox(c, x_left + 6, y + 17, emp.tagmulim_full, size=10)
        amount_text = f"על סך {_fmt_decimal(emp.tagmulim_amount)}" if emp.tagmulim_amount else "על סך _______"
        _text(c, x_left + tag_col_w / 2 + 14, y + 5, tag_col_w / 2 - 18, 14,
              amount_text, size=8, align="center")
        amt_checked = bool(emp.tagmulim_amount and not emp.tagmulim_full)
        _checkbox(c, x_left + tag_col_w / 2 + 2, y + 17, amt_checked, size=10)
        x_right = x_left
        x_left = x_right - pit_col_w
        _rect(c, x_left, y, pit_col_w, 26)
        # Render 3 mini-checkboxes for the per-employer tax mode.
        third = pit_col_w / 3
        for i, (label, key) in enumerate([("מס מלא", "full"), ("חלקי", "partial"), ("פטור", "exempt")]):
            cell_left = x_right - (i + 1) * third
            _text(c, cell_left + 18, y + 5, third - 22, 14, label, size=8, align="center")
            _checkbox(c, cell_left + 4, y + 17, eff_tax == key, size=10)
        y += 26

    y += 10
    y = _section_title(c, y, "הערות")
    _rect(c, MARGIN, y, inner_w, 40)


# ---------------------------------------------------------------------------
# Public API

def render_form_to_pdf(
    form: OperationForm,
    picture: Optional[ClientPicture],
    out_path: Path | str,
) -> Path:
    out_path = Path(out_path)
    out_path.write_bytes(render_form_to_bytes(form, picture))
    return out_path


def render_form_to_bytes(form: OperationForm, picture: Optional[ClientPicture]) -> bytes:
    _register_fonts_once()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("טופס תפעול")

    _render_cover(c, form)
    c.showPage()

    ops = list(form.operations)
    for i in range(form.max_operations):
        op = ops[i] if i < len(ops) else None
        _render_operation_page(c, form, op, i)
        c.showPage()

    c.save()
    return buf.getvalue()
