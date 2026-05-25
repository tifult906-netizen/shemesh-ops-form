from datetime import date
from decimal import Decimal
from pathlib import Path

from shemesh_ops.models import (
    BankAccount,
    ClientIdentity,
    ClientPicture,
    IDCard,
    OperationDetail,
    OperationForm,
    OperationFormCover,
)
from shemesh_ops.render import render_form_to_pdf
from shemesh_ops.render.form_builder import build_example_form
from shemesh_ops.review import deterministic_review, review_form
from shemesh_ops.unifier import ExtractionInputs, unify
from shemesh_ops.vision import MockVisionExtractor

ROOT = Path(__file__).resolve().parents[1]


def _bank() -> BankAccount:
    return BankAccount(
        holder_name="בן פורת אורי", id_number="029742590",
        bank_code="12", branch="549", account_number="383654",
        address="הפרדס 8, מולדת",
    )


def _picture() -> ClientPicture:
    return ClientPicture(
        identity=ClientIdentity(full_name="אורי בן פורת", id_number="029742590"),
        bank=_bank(),
        id_card=IDCard(full_name="אורי בן פורת", id_number="029742590", date_of_birth=date(1973, 2, 15)),
    )


def _good_form() -> OperationForm:
    cover = OperationFormCover(
        form_date=date(2026, 3, 15),
        client_id="029742590",
        client_first_name="אורי",
        client_last_name="בן פורת",
        amount_total=Decimal("2000"),
        amount_collected=Decimal("0"),
        payment_method="bank_transfer",
    )
    op = OperationDetail(
        insurance_company="מגדל", product_type="pension", kupa_number="29742590",
        money_types=["tagmulim"], tax_mode="full",
    )
    return OperationForm(cover=cover, operations=[op])


def test_clean_form_has_no_errors():
    findings = deterministic_review(_picture(), _good_form())
    errors = [f for f in findings if f.severity == "error"]
    assert errors == []


def test_id_mismatch_flagged_as_error():
    form = _good_form()
    form.cover.client_id = "999999999"
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


def test_full_review_via_mock_vision_does_not_block(tmp_path):
    """End-to-end: enriched picture + example form + mock LLM-review → no
    errors, render not blocked."""
    result = unify(
        ExtractionInputs(
            bank=ROOT / "אישור ניהול חשבון.pdf",
            tagmulim=ROOT / "דוח יתרות תגמולים.pdf",
            pitsuyim=ROOT / "דוח יתרות פיצויים.pdf",
            maslaka=ROOT / "דוח מסלקה.pdf",
            bl_history=ROOT / "אישור תקופות ביטוח ומעסיקים.pdf",
            id_front=ROOT / "WhatsApp Image 2026-05-24 at 13.45.41.jpeg",
            id_back=ROOT / "WhatsApp Image 2026-05-24 at 13.45.41 (1).jpeg",
        ),
        vision=MockVisionExtractor(),
    )
    form = build_example_form(result.picture)
    out_pdf = tmp_path / "form.pdf"
    render_form_to_pdf(form, result.picture, out_pdf)
    review = review_form(result.picture, form, str(out_pdf), MockVisionExtractor())
    assert not review.block_render(), [f.issue for f in review.findings if f.severity == "error"]
