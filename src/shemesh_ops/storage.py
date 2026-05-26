"""SQLite-backed submission storage.

Schema:
  submissions(
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,        -- ISO 8601
    rep_name TEXT,
    client_id TEXT NOT NULL,
    status TEXT NOT NULL,            -- 'draft' | 'reviewed' | 'sent'
    form_json TEXT NOT NULL,         -- serialized OperationForm
    picture_json TEXT NOT NULL,      -- serialized ClientPicture
    pdf_path TEXT,                   -- path to generated PDF on disk
    review_notes TEXT                -- JSON dump of ReviewFinding list (optional)
  )

Default DB path: ~/.shemesh-ops/submissions.db (override via SHEMESH_DB env
or the `db_path` constructor arg).

Pure stdlib (sqlite3 + json) — no extra deps.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Optional

from .models import ClientPicture, OperationForm
from .review import ReviewFinding

Status = Literal["draft", "reviewed", "sent"]

DEFAULT_DB_PATH = Path(os.environ.get(
    "SHEMESH_DB",
    str(Path.home() / ".shemesh-ops" / "submissions.db"),
))

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    rep_name     TEXT,
    client_id    TEXT    NOT NULL,
    status       TEXT    NOT NULL,
    form_json    TEXT    NOT NULL,
    picture_json TEXT    NOT NULL,
    pdf_path     TEXT,
    review_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_submissions_client_id ON submissions(client_id);
CREATE INDEX IF NOT EXISTS idx_submissions_created_at ON submissions(created_at);
"""


def _serialize(obj: Any) -> str:
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json()
    if is_dataclass(obj):
        return json.dumps(asdict(obj), default=str, ensure_ascii=False)
    return json.dumps(obj, default=str, ensure_ascii=False)


class SubmissionStore:
    def __init__(self, db_path: Optional[Path | str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save(
        self,
        form: OperationForm,
        picture: ClientPicture,
        *,
        pdf_path: Optional[Path | str] = None,
        review_findings: Optional[list[ReviewFinding]] = None,
        status: Status = "draft",
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        review_json = (
            json.dumps([asdict(f) for f in review_findings], ensure_ascii=False)
            if review_findings else None
        )
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO submissions
                   (created_at, rep_name, client_id, status, form_json, picture_json, pdf_path, review_notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    now,
                    form.cover.rep_name or None,
                    picture.identity.id_number,
                    status,
                    _serialize(form),
                    _serialize(picture),
                    str(pdf_path) if pdf_path else None,
                    review_json,
                ),
            )
            return cur.lastrowid

    def list_all(self, *, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                """SELECT id, created_at, rep_name, client_id, status, pdf_path
                   FROM submissions ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get(self, submission_id: int) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM submissions WHERE id = ?",
                (submission_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_status(self, submission_id: int, status: Status) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE submissions SET status = ? WHERE id = ?",
                (status, submission_id),
            )

    def delete(self, submission_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))

    def cleanup_old(self, *, max_age_days: int = 90) -> int:
        """Delete submissions older than `max_age_days` and remove their
        referenced PDF files from disk. Returns the count deleted.

        For privacy hygiene: by default an Israeli pension-withdrawal form
        contains client ת.ז + bank + employer history. Keeping that around
        forever isn't justifiable for a tool that's just a generation
        helper. Past the retention window, both the row and the PDF go.
        """
        cutoff_iso = (datetime.now() - timedelta(days=max_age_days)).isoformat(timespec="seconds")
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, pdf_path FROM submissions WHERE created_at < ?",
                (cutoff_iso,),
            ).fetchall()
            for row in rows:
                pdf_path = row["pdf_path"]
                if pdf_path:
                    try:
                        Path(pdf_path).unlink(missing_ok=True)
                    except OSError:
                        pass  # best effort; don't block the SQL delete
            c.execute("DELETE FROM submissions WHERE created_at < ?", (cutoff_iso,))
        return len(rows)
