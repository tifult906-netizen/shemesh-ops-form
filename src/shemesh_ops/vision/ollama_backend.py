"""Ollama-backed vision extractor — local inference via the Ollama daemon.

Setup:
    1. Install Ollama: https://ollama.com/download
    2. Pull a vision-capable model with reasonable Hebrew support:
         ollama pull qwen2.5vl:7b           # recommended
         ollama pull llama3.2-vision:11b    # alternative
    3. Start the daemon (Ollama runs on http://localhost:11434 by default).

Then in your code:
    extractor = OllamaVisionExtractor(model="qwen2.5vl:7b")

All extracted Hebrew labels are NOT trusted blindly — the model-review step
(see UNDERSTANDING.md §7 step 4.5) re-checks values before PDF render.
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

from .base import VisionExtractor

DEFAULT_MODEL = "qwen2.5vl:7b"
DEFAULT_HOST = "http://localhost:11434"


class OllamaVisionExtractor(VisionExtractor):
    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: float = 120.0,
    ):
        self.model = model or os.environ.get("SHEMESH_VISION_MODEL", DEFAULT_MODEL)
        self.host = (host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)).rstrip("/")
        self.timeout = timeout

    def extract(
        self,
        images: list[bytes],
        instruction: str,
        task_name: str = "",
    ) -> dict:
        import requests  # local import keeps the dep optional for mock-only use

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": instruction + "\n\nRespond with a single JSON object. No prose, no markdown fences.",
            "images": [base64.b64encode(img).decode("ascii") for img in images],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        resp = requests.post(
            f"{self.host}/api/generate", json=payload, timeout=self.timeout
        )
        resp.raise_for_status()
        body = resp.json().get("response", "").strip()
        return _parse_json_response(body)


def _parse_json_response(text: str) -> dict:
    """Parse JSON from a model response that may include code fences or prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise
