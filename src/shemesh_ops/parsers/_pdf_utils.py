"""Shared PDF helpers used by all parsers."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pdfplumber


def extract_raw_text(pdf_path: Path | str) -> str:
    """Return concatenated text from every page (RTL/CID quirks preserved)."""
    parts: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def parse_dmy(s: str) -> date:
    """Parse 'dd/mm/yyyy' or 'dd.mm.yyyy'."""
    s = s.strip().replace(".", "/")
    d, m, y = s.split("/")
    return date(int(y), int(m), int(d))
