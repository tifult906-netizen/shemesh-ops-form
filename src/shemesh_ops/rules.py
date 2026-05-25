"""Deterministic business rules for the form workflow.

Two main responsibilities:

1. **Tax-mode recommendations** (compute_tax_recommendation):
   - הוני money bucket → auto-locks to פטור ממס (capital → tax-free)
   - קרן השתלמות, source fund age ≥6 years → פטור ממס
   - קרן השתלמות, source fund age <6 years + תגמולים-הוני → 35% מס מלא
   - Cross-fund vintage override: if client has any other קה"ש ≥6yrs anywhere
     (even at a different management company), rep may use that vintage to
     make the <6yr withdrawal tax-free. We surface the override but never
     auto-apply it — the rep makes the call.

2. **קה"ש cross-fund vintage finder** (find_kahash_vintage_override):
   - Returns the oldest קה"ש fund the client owns that is ≥6 years old,
     or None.

These are pure functions over ClientPicture + OperationDetail (no I/O, no
LLM). Tested deterministically against the example customer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from .models import (
    ClientPicture,
    MaslakaFund,
    OperationDetail,
    TaxMode,
)

KAHASH_VINTAGE_THRESHOLD_YEARS = 6


@dataclass
class KahashVintageOverride:
    """A קה"ש fund the rep can use to override the 6-year tax rule on a
    different (<6yr) קה"ש withdrawal."""

    fund: MaslakaFund
    age_years: float


@dataclass
class TaxRecommendation:
    """Result of running tax rules over a proposed operation."""

    recommended_mode: TaxMode
    locked: bool
    reason: str
    # If the rep is withdrawing קה"ש <6yrs, surface whether a vintage override
    # is available so the UI can offer "use older fund's vintage" toggle.
    vintage_override_available: Optional[KahashVintageOverride] = None


# ---------------------------------------------------------------------------
# Helpers

def _years_between(start: date, end: date) -> float:
    """Approximate full years between two dates (365.25-day average year)."""
    days = (end - start).days
    return days / 365.25


def _kahash_funds(picture: ClientPicture) -> list[MaslakaFund]:
    if not picture.maslaka:
        return []
    return [f for f in picture.maslaka.funds if f.product_category == "study_fund"]


def find_kahash_vintage_override(
    picture: ClientPicture,
    current_source_fund: Optional[MaslakaFund],
    as_of: Optional[date] = None,
) -> Optional[KahashVintageOverride]:
    """Find the oldest קה"ש fund (other than the current source) that's
    ≥KAHASH_VINTAGE_THRESHOLD_YEARS old."""
    as_of = as_of or date.today()
    candidates: list[KahashVintageOverride] = []
    for f in _kahash_funds(picture):
        if current_source_fund and f.policy_number == current_source_fund.policy_number:
            continue
        if not f.plan_start_date:
            continue
        age = _years_between(f.plan_start_date, as_of)
        if age >= KAHASH_VINTAGE_THRESHOLD_YEARS:
            candidates.append(KahashVintageOverride(fund=f, age_years=age))
    if not candidates:
        return None
    # Return the oldest one (more "credit" for the override).
    candidates.sort(key=lambda c: c.age_years, reverse=True)
    return candidates[0]


def _find_source_maslaka_fund(
    picture: ClientPicture, operation: OperationDetail
) -> Optional[MaslakaFund]:
    if not picture.maslaka or not operation.kupa_number:
        return None
    for f in picture.maslaka.funds:
        if f.policy_number == operation.kupa_number:
            return f
    return None


def _source_has_hony_balance(
    picture: ClientPicture, operation: OperationDetail
) -> bool:
    """True if the source fund has a non-zero הוני bucket in the tagmulim report."""
    if not picture.tagmulim:
        return False
    tik = None
    source_fund = _find_source_maslaka_fund(picture, operation)
    if source_fund:
        tik = source_fund.tik_nikuim
    if not tik:
        return False
    for tag_fund in picture.tagmulim.funds:
        if tag_fund.tik_nikuim == tik and tag_fund.hony > Decimal(0):
            return True
    return False


# ---------------------------------------------------------------------------
# Public rule entrypoint

def compute_tax_recommendation(
    picture: ClientPicture,
    operation: OperationDetail,
    as_of: Optional[date] = None,
) -> TaxRecommendation:
    """Return the suggested tax mode + whether it's locked + the why."""
    as_of = as_of or date.today()
    source_fund = _find_source_maslaka_fund(picture, operation)

    # Rule 1: הוני money → auto-exempt regardless of product type.
    if "tagmulim" in operation.money_types and _source_has_hony_balance(picture, operation):
        return TaxRecommendation(
            recommended_mode="exempt",
            locked=True,
            reason="אוטומטי: הקופה כוללת רכיב הוני (פטור ממס כברירת מחדל)",
        )

    # Rule 2: קרן השתלמות 6-year rule
    if operation.product_type == "study_fund" and source_fund and source_fund.plan_start_date:
        age = _years_between(source_fund.plan_start_date, as_of)
        if age >= KAHASH_VINTAGE_THRESHOLD_YEARS:
            return TaxRecommendation(
                recommended_mode="exempt",
                locked=True,
                reason=f"קרן השתלמות בת {age:.1f} שנים (≥6) — פטור ממס",
            )
        # <6yrs — check for vintage override before locking to full-tax.
        override = find_kahash_vintage_override(picture, source_fund, as_of)
        if override:
            return TaxRecommendation(
                recommended_mode="full",  # default until rep accepts override
                locked=False,
                reason=(
                    f"קרן השתלמות בת {age:.1f} שנים — ברירת מחדל מס מלא (35%). "
                    f"קיים ותק חלופי בקופה {override.fund.policy_number} "
                    f"({override.age_years:.1f} שנים) — ניתן להפעיל לפטור"
                ),
                vintage_override_available=override,
            )
        return TaxRecommendation(
            recommended_mode="full",
            locked=True,
            reason=f"קרן השתלמות בת {age:.1f} שנים (<6) — מס מלא 35%",
        )

    # Default: no rule fires → rep picks freely, suggest full tax.
    return TaxRecommendation(
        recommended_mode="full",
        locked=False,
        reason="הרכב כספים סטנדרטי — הנציג בוחר את אופן המיסוי",
    )


def apply_tax_recommendation(
    operation: OperationDetail,
    recommendation: TaxRecommendation,
) -> None:
    """Mutate the operation to reflect the recommendation. Only overwrites
    tax_mode if it's locked OR currently unset; never overrides a rep's
    explicit choice on an unlocked recommendation."""
    if recommendation.locked or operation.tax_mode is None:
        operation.tax_mode = recommendation.recommended_mode
    if recommendation.locked:
        operation.tax_mode_locked_reason = recommendation.reason
    elif recommendation.vintage_override_available is not None:
        operation.tax_mode_locked_reason = recommendation.reason
    else:
        operation.tax_mode_locked_reason = None
