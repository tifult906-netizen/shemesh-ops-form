"""Vision extractor interface + PDF→PNG helper."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class VisionExtractor(ABC):
    """Pluggable vision backend. All callers go through `extract`."""

    @abstractmethod
    def extract(
        self,
        images: list[bytes],
        instruction: str,
        task_name: str = "",
    ) -> dict:
        """Send one or more images plus an instruction. Return a JSON dict
        with the requested fields.

        `task_name` is an opaque tag the Mock backend uses to find the right
        canned response; real backends ignore it.
        """


def render_pdf_pages(pdf_path: Path | str, page_indices: list[int], dpi: int = 150) -> list[bytes]:
    """Return PNG bytes for each requested 0-indexed page.

    Uses pdfplumber + Pillow (no pymupdf — pymupdf's native DLL is blocked
    by Windows Defender Application Control on some managed boxes).
    """
    import io
    import pdfplumber

    out: list[bytes] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i in page_indices:
            if i < 0 or i >= len(pdf.pages):
                raise IndexError(f"Page {i} out of range for {pdf_path} ({len(pdf.pages)} pages)")
            page_image = pdf.pages[i].to_image(resolution=dpi)
            buf = io.BytesIO()
            page_image.save(buf, format="PNG")
            out.append(buf.getvalue())
    return out


def pdf_page_count(pdf_path: Path | str) -> int:
    """Return the number of pages in a PDF without pymupdf."""
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        return len(pdf.pages)
