"""Demo CLI: feed the 5 PDFs + ID photos in, print unified JSON.

Usage:
    python -m shemesh_ops.cli \\
        --scan-dir . \\
        --vision mock

Vision backends:
  --vision none    no vision pass (Hebrew labels stay empty)
  --vision mock    hardcoded values for the example customer (default)
  --vision ollama  real local inference via Ollama daemon (set SHEMESH_VISION_MODEL
                   to choose a model; default: qwen2.5vl:7b)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from .render import render_form_to_pdf
from .render.form_builder import build_example_form
from .review import review_form
from .rules import apply_tax_recommendation, compute_tax_recommendation
from .storage import SubmissionStore
from .unifier import ExtractionInputs, unify
from .vision import MockVisionExtractor, OllamaVisionExtractor, VisionExtractor

DEFAULT_NAMES = {
    "bank":       "אישור ניהול חשבון.pdf",
    "tagmulim":   "דוח יתרות תגמולים.pdf",
    "pitsuyim":   "דוח יתרות פיצויים.pdf",
    "maslaka":    "דוח מסלקה.pdf",
    "bl":         "אישור תקופות ביטוח ומעסיקים.pdf",
    "id_front":   "WhatsApp Image 2026-05-24 at 13.45.41.jpeg",
    "id_back":    "WhatsApp Image 2026-05-24 at 13.45.41 (1).jpeg",
}


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value)}")


def _make_vision(name: str) -> VisionExtractor | None:
    if name == "none":
        return None
    if name == "mock":
        return MockVisionExtractor()
    if name == "ollama":
        return OllamaVisionExtractor()
    raise ValueError(f"Unknown vision backend: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bank", type=Path)
    parser.add_argument("--tagmulim", type=Path)
    parser.add_argument("--pitsuyim", type=Path)
    parser.add_argument("--maslaka", type=Path)
    parser.add_argument("--bl", type=Path)
    parser.add_argument("--id-front", type=Path)
    parser.add_argument("--id-back", type=Path)
    parser.add_argument("--scan-dir", type=Path, help="Look for default filenames in this directory")
    parser.add_argument("--vision", default="mock", choices=["none", "mock", "ollama"])
    parser.add_argument(
        "--render-form",
        type=Path,
        help="Also render the example operation form to this PDF path",
    )
    parser.add_argument(
        "--apply-tax-rules",
        action="store_true",
        help="Run tax-mode recommendations against each operation and apply them",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Run the model-review gate before rendering (blocks on errors)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the submission (form + picture + PDF path) to SQLite store",
    )
    args = parser.parse_args(argv)

    inputs = ExtractionInputs(
        bank=args.bank, tagmulim=args.tagmulim, pitsuyim=args.pitsuyim,
        maslaka=args.maslaka, bl_history=args.bl,
        id_front=args.id_front, id_back=args.id_back,
    )

    if args.scan_dir:
        defaults = {
            "bank":       inputs.bank,
            "tagmulim":   inputs.tagmulim,
            "pitsuyim":   inputs.pitsuyim,
            "maslaka":    inputs.maslaka,
            "bl_history": inputs.bl_history,
            "id_front":   inputs.id_front,
            "id_back":    inputs.id_back,
        }
        attr_to_fname = {
            "bank": "bank", "tagmulim": "tagmulim", "pitsuyim": "pitsuyim",
            "maslaka": "maslaka", "bl_history": "bl",
            "id_front": "id_front", "id_back": "id_back",
        }
        for attr, current in defaults.items():
            if current is None:
                candidate = args.scan_dir / DEFAULT_NAMES[attr_to_fname[attr]]
                if candidate.exists():
                    setattr(inputs, attr, candidate)

    if all(getattr(inputs, k) is None for k in (
        "bank", "tagmulim", "pitsuyim", "maslaka", "bl_history", "id_front", "id_back",
    )):
        parser.error("No inputs provided; use --scan-dir or pass specific files.")

    vision = _make_vision(args.vision)
    result = unify(inputs, vision=vision)

    out = {
        "client": result.picture.identity.model_dump(),
        "id_card": result.picture.id_card.model_dump() if result.picture.id_card else None,
        "bank": result.picture.bank.model_dump() if result.picture.bank else None,
        "tagmulim": result.picture.tagmulim.model_dump() if result.picture.tagmulim else None,
        "pitsuyim": result.picture.pitsuyim.model_dump() if result.picture.pitsuyim else None,
        "maslaka": result.picture.maslaka.model_dump() if result.picture.maslaka else None,
        "bl_history": result.picture.bl_history.model_dump() if result.picture.bl_history else None,
        "employer_xref": result.employer_xref,
        "notes": result.notes,
    }

    if args.render_form:
        form = build_example_form(result.picture)

        if args.apply_tax_rules:
            for op in form.operations:
                rec = compute_tax_recommendation(result.picture, op)
                apply_tax_recommendation(op, rec)
                sys.stderr.write(
                    f"[tax] op {op.kupa_number}: mode={op.tax_mode} "
                    f"(locked={rec.locked}) — {rec.reason}\n"
                )

        out_path = render_form_to_pdf(form, result.picture, args.render_form)
        sys.stderr.write(f"Form rendered to {out_path}\n")

        if args.review:
            review_result = review_form(result.picture, form, str(out_path), vision)
            out["review"] = [
                {"severity": f.severity, "field_path": f.field_path,
                 "issue": f.issue, "source": f.source}
                for f in review_result.findings
            ]
            if review_result.block_render():
                sys.stderr.write("[review] BLOCKED — fix errors before sending.\n")
            else:
                sys.stderr.write(
                    f"[review] {len(review_result.findings)} finding(s); no errors.\n"
                )

        if args.save:
            store = SubmissionStore()
            sid = store.save(
                form, result.picture,
                pdf_path=out_path,
                review_findings=(review_result.findings if args.review else None),
                status="reviewed" if args.review else "draft",
            )
            sys.stderr.write(f"[storage] saved submission #{sid}\n")
            out["submission_id"] = sid

    sys.stdout.reconfigure(encoding="utf-8")
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=_default)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
