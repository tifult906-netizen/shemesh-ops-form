"""OpenAI-backed vision extractor.

Trades local-only privacy for much better Hebrew extraction quality. The
images do leave the machine (sent to api.openai.com over HTTPS) — only
use this backend when that trade-off is acceptable for the use case.

Setup:
    pip install openai  (already in requirements.txt)
    set OPENAI_API_KEY=sk-...   # or SHEMESH_OPENAI_KEY
    set SHEMESH_VISION=openai
    set SHEMESH_VISION_MODEL=gpt-4o-mini   # default; gpt-4o for higher quality

Default model: gpt-4o-mini  (cheap + strong Hebrew + JSON-mode support)
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

from .base import VisionExtractor

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIVisionExtractor(VisionExtractor):
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 90.0,
    ):
        self.model = model or os.environ.get("SHEMESH_VISION_MODEL", DEFAULT_MODEL)
        self.api_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("SHEMESH_OPENAI_KEY")
        )
        self.timeout = timeout
        if not self.api_key:
            raise RuntimeError(
                "OpenAI vision backend requires OPENAI_API_KEY (or SHEMESH_OPENAI_KEY) env var"
            )

    def extract(
        self,
        images: list[bytes],
        instruction: str,
        task_name: str = "",
    ) -> dict:
        # Local import keeps openai optional for mock-only users.
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, timeout=self.timeout)

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    instruction
                    + "\n\nRespond with a single JSON object. No prose, no markdown fences."
                ),
            }
        ]
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64.b64encode(img).decode('ascii')}",
                    "detail": "high",
                },
            })

        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        return _parse_json_response(text)


def _parse_json_response(text: str) -> dict:
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
