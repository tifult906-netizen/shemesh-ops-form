"""Render an OperationForm to a Hebrew RTL PDF matching the reference layout.

Uses pymupdf direct drawing + python-bidi for RTL reordering. No HTML/CSS
pipeline (avoids GTK / wkhtmltopdf dependencies on Windows).
"""
from .renderer import render_form_to_pdf, render_form_to_bytes

__all__ = ["render_form_to_pdf", "render_form_to_bytes"]
