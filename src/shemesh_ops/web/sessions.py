"""In-memory + on-disk session state for the multi-step UI.

A session represents one client's in-progress draft. We keep:
  * raw uploads on disk under SESSION_ROOT/<id>/
  * the extracted ClientPicture in memory (rebuilt on demand from disk)
  * the in-progress OperationForm in memory

For now this is single-process and not threadsafe — fine for a single rep
running the dev server locally. Real deployment can swap in Redis/PG.
"""
from __future__ import annotations

import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..models import ClientPicture, OperationForm

SESSION_ROOT = Path(os.environ.get(
    "SHEMESH_SESSION_ROOT",
    str(Path.home() / ".shemesh-ops" / "sessions"),
)).resolve()

# Session IDs are always lowercase-hex tokens we generate ourselves (see
# `new()`). Anything that doesn't match this exact shape cannot be a real
# session and is rejected before it is ever used as a filesystem path —
# this is the primary guard against path traversal (e.g. "..", absolute
# paths, "a/b") on the public `/{sid}` route surface.
_SESSION_ID_RE = re.compile(r"\A[0-9a-f]{12}\Z")


def is_valid_session_id(sid: str) -> bool:
    """True iff `sid` is a well-formed session token (12 lowercase hex chars)."""
    return bool(_SESSION_ID_RE.match(sid or ""))


def _is_within(root: Path, candidate: Path) -> bool:
    """True iff `candidate` resolves to a path inside `root`."""
    try:
        candidate.resolve().relative_to(root)
        return True
    except (ValueError, OSError):
        return False


@dataclass
class Session:
    id: str
    upload_dir: Path
    picture: Optional[ClientPicture] = None
    form: Optional[OperationForm] = None
    pdf_path: Optional[Path] = None
    uploads: dict[str, Path] = field(default_factory=dict)  # logical name → file path


class SessionStore:
    def __init__(self) -> None:
        SESSION_ROOT.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, Session] = {}

    def new(self) -> Session:
        sid = uuid.uuid4().hex[:12]
        upload_dir = SESSION_ROOT / sid
        upload_dir.mkdir(parents=True, exist_ok=True)
        s = Session(id=sid, upload_dir=upload_dir)
        self._sessions[sid] = s
        return s

    def get(self, sid: str) -> Session:
        # Reject anything that isn't a token we could have minted. Without
        # this, a crafted `sid` ("..", "../../etc", an absolute path) would be
        # joined onto SESSION_ROOT and could point outside it.
        if not is_valid_session_id(sid):
            raise KeyError(f"Invalid session id {sid!r}")
        if sid not in self._sessions:
            # Rehydrate from disk if the session folder exists (e.g. after
            # server restart). Picture/form need to be rebuilt by callers.
            upload_dir = SESSION_ROOT / sid
            # Defence in depth: confirm the resolved path is still inside the
            # session root before trusting it.
            if upload_dir.is_dir() and _is_within(SESSION_ROOT, upload_dir):
                self._sessions[sid] = Session(id=sid, upload_dir=upload_dir)
            else:
                raise KeyError(f"Unknown session {sid!r}")
        return self._sessions[sid]


    def delete(self, sid: str) -> bool:
        """Forget a session and delete its upload folder. Returns whether
        anything was actually removed."""
        if not is_valid_session_id(sid):
            # Never let an unvalidated id reach shutil.rmtree.
            return False
        existed = sid in self._sessions
        self._sessions.pop(sid, None)
        folder = SESSION_ROOT / sid
        if folder.is_dir() and _is_within(SESSION_ROOT, folder):
            shutil.rmtree(folder, ignore_errors=True)
            existed = True
        return existed

    def active_count(self) -> int:
        """Number of sessions currently held in memory (for health probes)."""
        return len(self._sessions)

    def cleanup_old(self, *, max_age_seconds: int = 7 * 24 * 3600) -> int:
        """Remove session folders that haven't been touched in `max_age_seconds`.
        Returns the number of sessions deleted.
        """
        if not SESSION_ROOT.exists():
            return 0
        cutoff = time.time() - max_age_seconds
        removed = 0
        for child in SESSION_ROOT.iterdir():
            if not child.is_dir():
                continue
            try:
                if child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
                    self._sessions.pop(child.name, None)
                    removed += 1
            except OSError:
                continue
        return removed


# Module-level singleton — fine for single-process dev usage.
store = SessionStore()
