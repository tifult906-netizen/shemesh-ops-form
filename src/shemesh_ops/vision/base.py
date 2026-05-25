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
    """Return PNG bytes for each requested 0-indexed page."""
    import fitz

    out: list[bytes] = []
    with fitz.open(str(pdf_path)) as doc:
        for i in page_indices:
            if i < 0 or i >= len(doc):
                raise IndexError(f"Page {i} out of range for {pdf_path} ({len(doc)} pages)")
            pix = doc[i].get_pixmap(dpi=dpi)
            out.append(pix.tobytes("png"))
    return out
