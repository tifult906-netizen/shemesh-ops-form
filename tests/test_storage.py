from datetime import date
from decimal import Decimal
from pathlib import Path

from shemesh_ops.models import (
    BankAccount, ClientIdentity, ClientPicture, IDCard,
    OperationDetail, OperationForm, OperationFormCover,
)
from shemesh_ops.review import ReviewFinding
from shemesh_ops.storage import SubmissionStore


def _picture() -> ClientPicture:
    return ClientPicture(
        identity=ClientIdentity(full_name="אורי בן פורת", id_number="029742590"),
        bank=BankAccount(
            holder_name="בן פורת אורי", id_number="029742590",
            bank_code="12", branch="549", account_number="383654",
        ),
        id_card=IDCard(full_name="אורי בן פורת", id_number="029742590"),
    )


def _form() -> OperationForm:
    cover = OperationFormCover(
        form_date=date(2026, 3, 15),
        rep_name="אוהד",
        client_first_name="אורי",
        client_last_name="בן פורת",
        client_id="029742590",
        amount_total=Decimal("2000"),
    )
    op = OperationDetail(
        insurance_company="מגדל", product_type="pension", kupa_number="29742590",
        money_types=["tagmulim"], tax_mode="full",
    )
    return OperationForm(cover=cover, operations=[op])


def test_save_and_get(tmp_path):
    store = SubmissionStore(tmp_path / "test.db")
    pic = _picture()
    form = _form()
    sid = store.save(form, pic, pdf_path=tmp_path / "form.pdf", status="draft")
    assert isinstance(sid, int) and sid > 0

    row = store.get(sid)
    assert row is not None
    assert row["client_id"] == "029742590"
    assert row["rep_name"] == "אוהד"
    assert row["status"] == "draft"
    assert row["pdf_path"].endswith("form.pdf")


def test_list_returns_recent_first(tmp_path):
    store = SubmissionStore(tmp_path / "test.db")
    id1 = store.save(_form(), _picture(), status="draft")
    id2 = store.save(_form(), _picture(), status="draft")
    listed = store.list_all()
    assert [r["id"] for r in listed[:2]] == [id2, id1]


def test_update_status(tmp_path):
    store = SubmissionStore(tmp_path / "test.db")
    sid = store.save(_form(), _picture(), status="draft")
    store.update_status(sid, "sent")
    assert store.get(sid)["status"] == "sent"


def test_review_findings_persisted(tmp_path):
    store = SubmissionStore(tmp_path / "test.db")
    findings = [
        ReviewFinding(severity="warning", field_path="cover.notes", issue="ריק"),
    ]
    sid = store.save(_form(), _picture(), review_findings=findings)
    row = store.get(sid)
    import json as _json
    notes = _json.loads(row["review_notes"])
    assert notes[0]["severity"] == "warning"


def test_delete(tmp_path):
    store = SubmissionStore(tmp_path / "test.db")
    sid = store.save(_form(), _picture())
    store.delete(sid)
    assert store.get(sid) is None
