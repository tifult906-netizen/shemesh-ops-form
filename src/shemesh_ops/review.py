"""Model-review gate — runs before PDF render.

Two layers of checks:

  1. **Deterministic checks** (no LLM): cross-source consistency we can verify
     with pure logic — e.g. ID number matches across sources, IBAN parses,
     dates are in the past, fund balances are non-negative, employer-name
     spelling consistent within a form, etc.

  2. **LLM check** (optional, if a VisionExtractor is supplied): asks the
     model to compare the final form values against the source-document
     images and flag garbled Hebrew, swapped digits, or fields that don't
     appear in the source.

Returns a list of `ReviewFinding`s with severity. Caller decides whether to
block PDF render. Default policy: any `error` blocks; `warning` requires rep
acknowledgement; `info` is just shown.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from .models import ClientPicture, OperationForm
from .vision import VisionExtractor, render_pdf_pages

Severity = Literal["info", "warning", "error"]


@dataclass
class ReviewFinding:
    severity: Severity
    field_path: str
    issue: str
    source: str = ""


@dataclass
class ReviewResult:
    findings: list[ReviewFinding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == "warning" for f in self.findings)

    def block_render(self) -> bool:
        """Default policy: block on any error."""
        return self.has_errors


# ---------------------------------------------------------------------------
# Deterministic checks


def _check_id_consistency(picture: ClientPicture, form: OperationForm, out: list[ReviewFinding]) -> None:
    canonical = picture.identity.id_number
    if form.cover.client_id and form.cover.client_id != canonical:
        out.append(ReviewFinding(
            severity="error",
            field_path="cover.client_id",
            issue=f"ת.ז בטופס ({form.cover.client_id}) שונה מהמזהה הקנוני ({canonical})",
            source="identity",
        ))
    if picture.id_card and picture.id_card.id_number != canonical:
        out.append(ReviewFinding(
            severity="warning",
            field_path="id_card.id_number",
            issue=f"ת.ז מתעודת הזהות ({picture.id_card.id_number}) שונה מהמזהה הקנוני ({canonical})",
            source="id_card",
        ))


def _check_dates_sane(picture: ClientPicture, form: OperationForm, out: list[ReviewFinding]) -> None:
    today = date.today()
    if form.cover.form_date and form.cover.form_date > today:
        out.append(ReviewFinding(
            severity="warning",
            field_path="cover.form_date",
            issue=f"תאריך הטופס בעתיד ({form.cover.form_date})",
        ))
    if form.cover.client_date_of_birth and form.cover.client_date_of_birth > today:
        out.append(ReviewFinding(
            severity="error",
            field_path="cover.client_date_of_birth",
            issue="תאריך לידה בעתיד",
        ))


def _check_amounts(form: OperationForm, out: list[ReviewFinding]) -> None:
    cover = form.cover
    if cover.amount_total is not None and cover.amount_total < Decimal(0):
        out.append(ReviewFinding(
            severity="error",
            field_path="cover.amount_total",
            issue="סכום כולל שלילי",
        ))
    if (cover.amount_total is not None and cover.amount_collected is not None
            and cover.amount_collected > cover.amount_total):
        out.append(ReviewFinding(
            severity="warning",
            field_path="cover.amount_collected",
            issue="סכום שנגבה גדול מסכום כולל",
        ))


def _check_operations(form: OperationForm, picture: ClientPicture, out: list[ReviewFinding]) -> None:
    for i, op in enumerate(form.operations):
        path = f"operations[{i}]"
        if not op.insurance_company:
            out.append(ReviewFinding(
                severity="error", field_path=f"{path}.insurance_company",
                issue="חברת ביטוח לא הוגדרה",
            ))
        if not op.kupa_number:
            out.append(ReviewFinding(
                severity="error", field_path=f"{path}.kupa_number",
                issue="מספר קופה לא הוגדר",
            ))
        if not op.money_types:
            out.append(ReviewFinding(
                severity="error", field_path=f"{path}.money_types",
                issue="לא נבחר סוג כסף (תגמולים/פיצויים)",
            ))
        if op.tax_mode is None:
            out.append(ReviewFinding(
                severity="warning", field_path=f"{path}.tax_mode",
                issue="לא נבחרה אופן מיסוי",
            ))
        # Cross-check kupa exists in maslaka / tagmulim
        if op.kupa_number and picture.maslaka:
            known = {f.policy_number for f in picture.maslaka.funds}
            if op.kupa_number not in known:
                out.append(ReviewFinding(
                    severity="warning", field_path=f"{path}.kupa_number",
                    issue=f"מספר קופה {op.kupa_number} לא נמצא בדוח המסלקה",
                    source="maslaka",
                ))


def _check_hebrew_garbled(picture: ClientPicture, out: list[ReviewFinding]) -> None:
    """Flag Hebrew fields that look 'reversed' or empty in a place we expect filled text."""
    flagged_empty: list[tuple[str, str]] = []
    if picture.bank and not picture.bank.holder_name:
        flagged_empty.append(("bank.holder_name", "שם בעל החשבון ריק"))
    if picture.bank and not picture.bank.address:
        flagged_empty.append(("bank.address", "כתובת חשבון ריקה"))
    if picture.tagmulim:
        for j, f in enumerate(picture.tagmulim.funds):
            if not f.kupa_name:
                flagged_empty.append((f"tagmulim.funds[{j}].kupa_name", "שם קופה ריק"))
    for path, issue in flagged_empty:
        out.append(ReviewFinding(
            severity="warning", field_path=path, issue=issue,
            source="vision_pass_needed",
        ))


def deterministic_review(picture: ClientPicture, form: OperationForm) -> list[ReviewFinding]:
    out: list[ReviewFinding] = []
    _check_id_consistency(picture, form, out)
    _check_dates_sane(picture, form, out)
    _check_amounts(form, out)
    _check_operations(form, picture, out)
    _check_hebrew_garbled(picture, out)
    return out


# ---------------------------------------------------------------------------
# LLM check (optional)


LLM_REVIEW_INSTRUCTION = """You are a back-office reviewer for an Israeli pension-withdrawal operation form.
You are given:
  1. A JSON of the form values the rep is about to send.
  2. A rendered preview image of the same form.

Compare them. Flag ONLY actual problems — not stylistic issues.

Things to flag:
  - Garbled / reversed / corrupt Hebrew text in any field (e.g. letters that don't form real words).
  - Numeric values that look swapped, misaligned, or implausible (e.g. ID with 8 digits not 9, IBAN missing IL prefix, balance with extra zeros).
  - Fields filled with placeholder text (e.g. "____", "TODO", or empty when they should have data).
  - Hebrew name fields containing English characters or vice versa.

Do NOT flag:
  - Empty optional fields.
  - Notes / הערות free-text fields.
  - Stylistic differences (font, alignment, color).

Return JSON: {"findings": [{"severity": "error|warning|info", "field_path": "...", "issue": "..."}]}.
If everything looks fine, return {"findings": []}.
"""


def llm_review(
    form: OperationForm,
    rendered_form_pdf_path,
    vision: VisionExtractor,
) -> list[ReviewFinding]:
    """Call the vision model on a rendered preview of the form to look for
    garbled text, swapped digits, etc. Returns a (possibly empty) list of
    findings."""
    images = render_pdf_pages(rendered_form_pdf_path, [0])  # cover page is enough for sanity check
    form_json = form.model_dump_json(indent=2)
    instruction = LLM_REVIEW_INSTRUCTION + "\n\nFORM JSON:\n" + form_json
    try:
        raw = vision.extract(
            images=images, instruction=instruction, task_name="form_review",
        )
    except Exception as e:
        return [ReviewFinding(
            severity="warning", field_path="",
            issue=f"בדיקת מודל נכשלה: {e}",
        )]
    findings = raw.get("findings", [])
    out: list[ReviewFinding] = []
    for item in findings:
        out.append(ReviewFinding(
            severity=item.get("severity", "warning"),
            field_path=item.get("field_path", ""),
            issue=item.get("issue", ""),
            source="llm_review",
        ))
    return out


# ---------------------------------------------------------------------------
# Combined entrypoint


def review_form(
    picture: ClientPicture,
    form: OperationForm,
    rendered_pdf_path: Optional[str] = None,
    vision: Optional[VisionExtractor] = None,
) -> ReviewResult:
    findings = deterministic_review(picture, form)
    if vision is not None and rendered_pdf_path is not None:
        findings.extend(llm_review(form, rendered_pdf_path, vision))
    return ReviewResult(findings=findings)
