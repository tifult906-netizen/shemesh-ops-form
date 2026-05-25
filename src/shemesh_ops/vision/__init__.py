"""Vision extractors — pluggable backends for OCR'ing PDF page images and
ID-card photos. The mock backend returns hardcoded values for the example
customer (no GPU needed). The ollama backend talks to a locally-running
Ollama daemon with a multimodal model.

Public API:
    VisionExtractor (ABC)
    MockVisionExtractor
    OllamaVisionExtractor
    render_pdf_pages(pdf_path, indices) -> list[bytes]
"""
from .base import VisionExtractor, render_pdf_pages
from .mock import MockVisionExtractor
from .ollama_backend import OllamaVisionExtractor
from .openai_backend import OpenAIVisionExtractor

__all__ = [
    "VisionExtractor",
    "MockVisionExtractor",
    "OllamaVisionExtractor",
    "OpenAIVisionExtractor",
    "render_pdf_pages",
]
