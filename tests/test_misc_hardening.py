"""Tests for hardening helpers added in the 2026-06-07 audit:
  * Israeli ID check-digit validation + its review finding,
  * the PDF renderer's font fallback (must never crash on a missing TTF).
"""
from __future__ import annotations

from datetime import date

from shemesh_ops.models import (
    BankAccount,
    ClientIdentity,
    ClientPicture,
    IDCard,
    OperationDetail,
    OperationForm,
    OperationFormCover,
)
from shemesh_ops.review import deterministic_review, is_valid_israeli_id


# ---------------------------------------------------------------------------
# Israeli ID check digit


def test_valid_israeli_ids():
    assert is_valid_israeli_id("123456782")   # canonical valid sample
    assert is_valid_israeli_id("000000000")
    # 8-digit form gets left-padded to 9 before validation: "12345678" -> "012345678".
    assert is_valid_israeli_id("12345678") == is_valid_israeli_id("012345678")


def test_invalid_israeli_ids():
    assert not is_valid_israeli_id("999999999")   # bad check digit
    assert not is_valid_israeli_id("123456789")   # bad check digit
    assert not is_valid_israeli_id("12345")       # implausible but still checked
    assert not is_valid_israeli_id("")            # empty
    assert not is_valid_israeli_id("12abc6782")   # non-numeric
    assert not is_valid_israeli_id("1234567890")  # too long (>9)


def _picture(id_number: str) -> ClientPicture:
    return ClientPicture(
        identity=ClientIdentity(full_name="x", id_number=id_number),
        bank=BankAccount(
            holder_name="x", id_number=id_number,
            bank_code="12", branch="549", account_number="9999999",
            address="עיר",
        ),
        id_card=IDCard(full_name="x", id_number=id_number, date_of_birth=date(1980, 1, 1)),
    )


def _form(id_number: str) -> OperationForm:
    return OperationForm(
        cover=OperationFormCover(form_date=date(2026, 1, 1), client_id=id_number),
        operations=[OperationDetail(
            insurance_company="חברה דוגמה ב", product_type="pension",
            kupa_number="POL", money_types=["tagmulim"], tax_mode="full",
        )],
    )


def test_review_flags_bad_check_digit_as_warning_not_error():
    findings = deterministic_review(_picture("999999999"), _form("999999999"))
    cd = [f for f in findings if f.source == "checkdigit"]
    assert len(cd) == 1
    assert cd[0].severity == "warning"  # must NOT block the form


def test_review_no_checkdigit_finding_for_valid_id():
    findings = deterministic_review(_picture("123456782"), _form("123456782"))
    assert not any(f.source == "checkdigit" for f in findings)


# ---------------------------------------------------------------------------
# Renderer font fallback


def test_renderer_survives_missing_font(monkeypatch):
    # Point both fonts at non-existent paths and force re-registration.
    import shemesh_ops.render.renderer as r
    monkeypatch.setattr(r, "FONT_FILE", "/no/such/font.ttf")
    monkeypatch.setattr(r, "FONT_BOLD_FILE", "/no/such/font-bold.ttf")
    monkeypatch.setattr(r, "_fonts_registered", False)
    monkeypatch.setattr(r, "_FALLBACK_ALIAS", {})

    pic = _picture("123456782")
    out = r.render_form_to_bytes(_form("123456782"), pic)
    assert out.startswith(b"%PDF-")
    assert len(out) > 1000
