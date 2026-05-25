from datetime import date
from decimal import Decimal

from shemesh_ops.models import (
    BankAccount,
    ClientIdentity,
    ClientPicture,
    IDCard,
    OperationDetail,
    OperationForm,
    OperationFormCover,
)
from shemesh_ops.review import deterministic_review


def _bank() -> BankAccount:
    return BankAccount(
        holder_name="ישראלי ישראל", id_number="999999999",
        bank_code="12", branch="549", account_number="9999999",
        address="רחוב הדוגמה 1, עיר",
    )


def _picture() -> ClientPicture:
    return ClientPicture(
        identity=ClientIdentity(full_name="ישראל ישראלי", id_number="999999999"),
        bank=_bank(),
        id_card=IDCard(full_name="ישראל ישראלי", id_number="999999999", date_of_birth=date(1973, 2, 15)),
    )


def _good_form() -> OperationForm:
    cover = OperationFormCover(
        form_date=date(2026, 3, 15),
        client_id="999999999",
        client_first_name="ישראל",
        client_last_name="ישראלי",
        amount_total=Decimal("2000"),
        amount_collected=Decimal("0"),
        payment_method="bank_transfer",
    )
    op = OperationDetail(
        insurance_company="חברה דוגמה ב", product_type="pension", kupa_number="999999999",
        money_types=["tagmulim"], tax_mode="full",
    )
    return OperationForm(cover=cover, operations=[op])


def test_clean_form_has_no_errors():
    findings = deterministic_review(_picture(), _good_form())
    errors = [f for f in findings if f.severity == "error"]
    assert errors == []


def test_id_mismatch_flagged_as_error():
    form = _good_form()
    form.cover.client_id = "111111111"  # canonical is 999999999
    findings = deterministic_review(_picture(), form)
    assert any(f.severity == "error" and "ת.ז" in f.issue for f in findings)


def test_missing_kupa_number_is_error():
    form = _good_form()
    form.operations[0].kupa_number = ""
    findings = deterministic_review(_picture(), form)
    assert any(f.severity == "error" and "קופה" in f.issue for f in findings)


def test_missing_money_type_is_error():
    form = _good_form()
    form.operations[0].money_types = []
    findings = deterministic_review(_picture(), form)
    assert any(f.severity == "error" and "סוג כסף" in f.issue for f in findings)


def test_dob_in_future_is_error():
    form = _good_form()
    form.cover.client_date_of_birth = date(2099, 1, 1)
    findings = deterministic_review(_picture(), form)
    assert any(f.severity == "error" and "לידה" in f.issue for f in findings)


def test_amount_collected_over_total_is_warning():
    form = _good_form()
    form.cover.amount_total = Decimal("1000")
    form.cover.amount_collected = Decimal("2000")
    findings = deterministic_review(_picture(), form)
    assert any(f.severity == "warning" and "שנגבה" in f.issue for f in findings)


def test_empty_hebrew_labels_flagged():
    p = _picture()
    p.bank.holder_name = ""
    p.bank.address = ""
    findings = deterministic_review(p, _good_form())
    assert any("holder_name" in f.field_path for f in findings)
    assert any("address" in f.field_path for f in findings)
