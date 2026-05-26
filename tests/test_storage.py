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
        identity=ClientIdentity(full_name="ישראל ישראלי", id_number="999999999"),
        bank=BankAccount(
            holder_name="ישראלי ישראל", id_number="999999999",
            bank_code="12", branch="549", account_number="9999999",
        ),
        id_card=IDCard(full_name="ישראל ישראלי", id_number="999999999"),
    )


def _form() -> OperationForm:
    cover = OperationFormCover(
        form_date=date(2026, 3, 15),
        rep_name="נציג לדוגמה",
        client_first_name="ישראל",
        client_last_name="ישראלי",
        client_id="999999999",
        amount_total=Decimal("2000"),
    )
    op = OperationDetail(
        insurance_company="חברה דוגמה ב", product_type="pension", kupa_number="999999999",
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
    assert row["client_id"] == "999999999"
    assert row["rep_name"] == "נציג לדוגמה"
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


def test_cleanup_old_purges_rows_and_pdfs(tmp_path):
    """`cleanup_old(max_age_days=N)` removes submissions older than N days
    AND deletes their referenced PDF files from disk."""
    import sqlite3
    store = SubmissionStore(tmp_path / "test.db")

    # 1) An "old" submission with a PDF file on disk.
    old_pdf = tmp_path / "old.pdf"
    old_pdf.write_bytes(b"%PDF-1.4\nold")
    sid_old = store.save(_form(), _picture(), pdf_path=old_pdf)
    # Hack the created_at backwards so it falls outside the retention window.
    with sqlite3.connect(str(tmp_path / "test.db")) as conn:
        conn.execute(
            "UPDATE submissions SET created_at = '2020-01-01T00:00:00' WHERE id = ?",
            (sid_old,),
        )

    # 2) A "fresh" submission — should survive cleanup.
    fresh_pdf = tmp_path / "fresh.pdf"
    fresh_pdf.write_bytes(b"%PDF-1.4\nfresh")
    sid_fresh = store.save(_form(), _picture(), pdf_path=fresh_pdf)

    removed = store.cleanup_old(max_age_days=30)
    assert removed == 1

    assert store.get(sid_old) is None        # row deleted
    assert not old_pdf.exists()              # PDF gone too
    assert store.get(sid_fresh) is not None  # fresh one untouched
    assert fresh_pdf.exists()


def test_cleanup_old_handles_missing_pdf_gracefully(tmp_path):
    """If the PDF file is already gone (manual delete, disk move), the
    SQL delete should still complete and the row should be removed."""
    import sqlite3
    store = SubmissionStore(tmp_path / "test.db")
    sid = store.save(_form(), _picture(), pdf_path=tmp_path / "does-not-exist.pdf")
    with sqlite3.connect(str(tmp_path / "test.db")) as conn:
        conn.execute(
            "UPDATE submissions SET created_at = '2020-01-01T00:00:00' WHERE id = ?",
            (sid,),
        )
    removed = store.cleanup_old(max_age_days=30)
    assert removed == 1
    assert store.get(sid) is None
