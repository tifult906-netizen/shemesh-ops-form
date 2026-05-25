"""Required-documents engine.

Given a proposed OperationDetail + the ClientPicture + per-employer 161/release
status (provided by the rep, since it's external info), return the list of
documents that MUST be attached for this withdrawal to be processed.

Mirrors `מסמכים נדרשים לכל פעולה.docx` (the rules sheet you provided) — see
UNDERSTANDING.md §3 for the canonical rule list.

Pure function, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from .models import ClientPicture, OperationDetail

DocKey = Literal[
    "id_front",
    "id_back_or_sefach",
    "bank_confirmation",
    "form_161",
    "tax_confirmation",
    "employment_end",
    "retzef_employers",
    "funds_release",
    "bl_employment_history",
]

# Companies that require 2 years (not 1) since employment end before רצף is valid.
EXTENDED_RETZEF_COMPANIES = ("אלטשולר", "הראל")
RETZEF_MIN_YEARS_DEFAULT = 1
RETZEF_MIN_YEARS_EXTENDED = 2
AGE_THRESHOLD_NO_EMPLOYMENT_END = 60
FUNDS_RELEASE_WINDOW_MONTHS = 4


@dataclass
class EmployerReleaseStatus:
    """What the rep knows about a particular employer's paperwork."""

    employer_name: str
    employer_id: Optional[str] = None
    has_161: bool = False
    has_funds_release: bool = False
    employment_end_date: Optional[date] = None


@dataclass
class RequiredDoc:
    key: DocKey
    label_he: str
    required: bool
    reason: str


@dataclass
class ChecklistResult:
    docs: list[RequiredDoc] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def required_keys(self) -> set[DocKey]:
        return {d.key for d in self.docs if d.required}


def _client_age_years(picture: ClientPicture, as_of: date) -> Optional[float]:
    dob = picture.id_card.date_of_birth if picture.id_card else None
    if not dob:
        return None
    return (as_of - dob).days / 365.25


def _months_since(d: date, as_of: date) -> float:
    return (as_of - d).days / 30.4375


def _retzef_min_years(insurance_company: str) -> int:
    if any(c in insurance_company for c in EXTENDED_RETZEF_COMPANIES):
        return RETZEF_MIN_YEARS_EXTENDED
    return RETZEF_MIN_YEARS_DEFAULT


def required_documents(
    operation: OperationDetail,
    picture: ClientPicture,
    employer_release: Optional[list[EmployerReleaseStatus]] = None,
    as_of: Optional[date] = None,
) -> ChecklistResult:
    """Compute the doc checklist for one פעולה."""
    as_of = as_of or date.today()
    employer_release = employer_release or []
    result = ChecklistResult()
    age = _client_age_years(picture, as_of)

    # Base docs always required ----------------------------------------------
    result.docs.append(RequiredDoc(
        key="id_front", label_he="ת.ז קדמי",
        required=True, reason="בסיס לכל פעולה",
    ))
    result.docs.append(RequiredDoc(
        key="id_back_or_sefach",
        label_he='ת.ז אחורי (ביומטרי) או ספח (ת"ז ישן)',
        required=True, reason="בסיס לכל פעולה",
    ))
    result.docs.append(RequiredDoc(
        key="bank_confirmation",
        label_he='אישור ניהול חשבון / צ\'ק מבוטל',
        required=True, reason="לזיהוי חשבון יעד התשלום",
    ))

    # Money-type-specific docs -----------------------------------------------
    if "tagmulim" in operation.money_types or "pitsuyim" in operation.money_types:
        # Default-required for withdrawal — waived only if client ≥60.
        if age is None or age < AGE_THRESHOLD_NO_EMPLOYMENT_END:
            min_years = _retzef_min_years(operation.insurance_company)
            why_retzef = (
                f"רצף תקף רק לאחר {min_years} שנים מסיום העסקה"
                if min_years > 1 else
                "רצף תקף רק לאחר שנה מסיום העסקה"
            )
            result.docs.append(RequiredDoc(
                key="employment_end",
                label_he="סיום העסקה",
                required=True,
                reason="לקוח מתחת לגיל 60 — חייב לתעד סיום העסקה",
            ))
            result.docs.append(RequiredDoc(
                key="retzef_employers",
                label_he="רצף מעסיקים",
                required=True,
                reason=f"חלופה לסיום העסקה — {why_retzef}",
            ))
        else:
            result.notes.append(
                f"לקוח בן {age:.0f} (≥60) — אין צורך בסיום העסקה / רצף"
            )

    # פיצויים-only extras ---------------------------------------------------
    if "pitsuyim" in operation.money_types:
        result.docs.append(RequiredDoc(
            key="form_161",
            label_he='טופס 161 / אישור מס פיצויים',
            required=True,
            reason="חובה למשיכת פיצויים",
        ))
        # שחרור כספים — required when ANY of the selected employers ended work
        # in the last 4 months (or rep didn't supply that info)
        needs_release = False
        release_reason = "לא צוין תאריך סיום עבור המעסיק/ים"
        if employer_release:
            for status in employer_release:
                if status.has_funds_release:
                    continue
                if status.employment_end_date and _months_since(status.employment_end_date, as_of) < FUNDS_RELEASE_WINDOW_MONTHS:
                    needs_release = True
                    release_reason = (
                        f"פחות מ-{FUNDS_RELEASE_WINDOW_MONTHS} חודשים מסיום העסקה "
                        f"אצל {status.employer_name}"
                    )
                    break
        else:
            needs_release = True
        if needs_release:
            result.docs.append(RequiredDoc(
                key="funds_release",
                label_he="שחרור כספים",
                required=True,
                reason=release_reason,
            ))

    # BL employment-history fallback — required when client<60 AND any
    # selected employer lacks 161 / שחרור.
    if age is not None and age < AGE_THRESHOLD_NO_EMPLOYMENT_END and employer_release:
        any_missing = any(
            (not s.has_161) and (not s.has_funds_release)
            for s in employer_release
        )
        if any_missing:
            offending = [
                s.employer_name for s in employer_release
                if not s.has_161 and not s.has_funds_release
            ]
            result.docs.append(RequiredDoc(
                key="bl_employment_history",
                label_he="אישור תקופות ביטוח ומעסיקים (ביטוח לאומי)",
                required=True,
                reason=(
                    "מעסיק/ים חסרים 161/שחרור: "
                    + ", ".join(offending)
                ),
            ))

    return result
