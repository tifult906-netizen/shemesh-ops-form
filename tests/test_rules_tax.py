"""Tests for the tax-mode rules. Constructs synthetic ClientPicture instances
to exercise each branch deterministically."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from shemesh_ops.models import (
    BankAccount,
    ClientIdentity,
    ClientPicture,
    MaslakaFund,
    MaslakaReport,
    OperationDetail,
    TagmulimFundRow,
    TagmulimReport,
)
from shemesh_ops.rules import (
    KAHASH_VINTAGE_THRESHOLD_YEARS,
    compute_tax_recommendation,
    find_kahash_vintage_override,
)


def _empty_bank() -> BankAccount:
    return BankAccount(
        holder_name="", id_number="000000000", bank_code="", branch="", account_number=""
    )


def _picture_with_kahash_funds(*funds: MaslakaFund) -> ClientPicture:
    return ClientPicture(
        identity=ClientIdentity(full_name="", id_number="000000000"),
        bank=_empty_bank(),
        maslaka=MaslakaReport(
            client=ClientIdentity(full_name="", id_number="000000000"),
            funds=list(funds),
        ),
    )


def _kahash(policy: str, start_date: date, tik: str = "936000000") -> MaslakaFund:
    return MaslakaFund(
        management_company="", product_category="study_fund",
        policy_number=policy, total_balance=Decimal("10000"),
        plan_start_date=start_date, tik_nikuim=tik,
    )


# --- Rule 1: הוני bucket → auto-exempt -----------------------------------


def test_hony_balance_auto_locks_to_exempt():
    """If the source fund has any הוני balance, tax_mode is locked to exempt."""
    pic = ClientPicture(
        identity=ClientIdentity(full_name="", id_number="000000000"),
        bank=_empty_bank(),
        maslaka=MaslakaReport(
            client=ClientIdentity(full_name="", id_number="000000000"),
            funds=[MaslakaFund(
                management_company="", product_category="new_pension",
                policy_number="POLICY1", total_balance=Decimal("100000"),
                tik_nikuim="935111111",
            )],
        ),
        tagmulim=TagmulimReport(
            client=ClientIdentity(full_name="", id_number="000000000"),
            funds=[TagmulimFundRow(
                tik_nikuim="935111111", kupa_name="", total=Decimal("100000"),
                hony=Decimal("50000"),
            )],
            grand_total=Decimal("100000"),
        ),
    )
    op = OperationDetail(kupa_number="POLICY1", product_type="pension", money_types=["tagmulim"])
    rec = compute_tax_recommendation(pic, op)
    assert rec.recommended_mode == "exempt"
    assert rec.locked is True
    assert "הוני" in rec.reason


# --- Rule 2: קה"ש ≥6 years → exempt --------------------------------------


def test_old_kahash_locks_to_exempt():
    """A קה"ש fund >=6 years old → automatic exempt."""
    today = date(2026, 5, 24)
    pic = _picture_with_kahash_funds(
        _kahash("KAHASH_OLD", date(2018, 1, 1))
    )
    op = OperationDetail(kupa_number="KAHASH_OLD", product_type="study_fund", money_types=["tagmulim"])
    rec = compute_tax_recommendation(pic, op, as_of=today)
    assert rec.recommended_mode == "exempt"
    assert rec.locked is True
    assert "6" in rec.reason or "פטור" in rec.reason


# --- Rule 3: קה"ש <6 years, no override → full-tax locked ----------------


def test_young_kahash_no_override_locks_to_full():
    today = date(2026, 5, 24)
    pic = _picture_with_kahash_funds(
        _kahash("KAHASH_NEW", date(2025, 1, 1))
    )
    op = OperationDetail(kupa_number="KAHASH_NEW", product_type="study_fund", money_types=["tagmulim"])
    rec = compute_tax_recommendation(pic, op, as_of=today)
    assert rec.recommended_mode == "full"
    assert rec.locked is True
    assert rec.vintage_override_available is None
    assert "35" in rec.reason or "מס מלא" in rec.reason


# --- Rule 4: קה"ש <6 years WITH override available → unlocked, hint ------


def test_young_kahash_with_older_override_unlocked():
    today = date(2026, 5, 24)
    pic = _picture_with_kahash_funds(
        _kahash("KAHASH_NEW", date(2025, 1, 1)),
        _kahash("KAHASH_OLD_OTHER", date(2015, 6, 1), tik="936999999"),
    )
    op = OperationDetail(kupa_number="KAHASH_NEW", product_type="study_fund", money_types=["tagmulim"])
    rec = compute_tax_recommendation(pic, op, as_of=today)
    assert rec.recommended_mode == "full"   # default until rep accepts
    assert rec.locked is False              # not locked — rep can flip to exempt
    assert rec.vintage_override_available is not None
    assert rec.vintage_override_available.fund.policy_number == "KAHASH_OLD_OTHER"
    assert rec.vintage_override_available.age_years >= KAHASH_VINTAGE_THRESHOLD_YEARS


# --- Default: nothing fires → unlocked, suggest full ---------------------


def test_default_no_rule_fires():
    pic = ClientPicture(
        identity=ClientIdentity(full_name="", id_number="000000000"),
        bank=_empty_bank(),
    )
    op = OperationDetail(kupa_number="UNKNOWN", product_type="pension", money_types=["pitsuyim"])
    rec = compute_tax_recommendation(pic, op)
    assert rec.recommended_mode == "full"
    assert rec.locked is False
    assert rec.vintage_override_available is None


# --- Override finder on its own ------------------------------------------


def test_find_kahash_override_picks_oldest():
    today = date(2026, 5, 24)
    pic = _picture_with_kahash_funds(
        _kahash("A", date(2010, 1, 1)),
        _kahash("B", date(2017, 1, 1)),
        _kahash("C", date(2024, 1, 1)),
    )
    # current source = C (the youngest); A and B both qualify, A is older.
    current = pic.maslaka.funds[2]
    override = find_kahash_vintage_override(pic, current, as_of=today)
    assert override is not None
    assert override.fund.policy_number == "A"


