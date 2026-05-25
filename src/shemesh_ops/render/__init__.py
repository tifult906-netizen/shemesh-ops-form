"""Render an OperationForm to a Hebrew RTL PDF matching the reference layout.

Uses reportlab.canvas for PDF drawing + python-bidi for RTL reordering.
No native binary deps (works on machines with Windows Defender Application
Control blocking unsigned DLLs like pymupdf's _mupdf.pyd).
"""
from .renderer import render_form_to_pdf, render_form_to_bytes

__all__ = ["render_form_to_pdf", "render_form_to_bytes"]
