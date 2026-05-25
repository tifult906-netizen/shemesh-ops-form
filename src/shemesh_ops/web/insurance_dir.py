"""Lookup helpers for the insurance-companies CSV (company × product → email).

The CSV path is configurable via the `SHEMESH_INSURANCE_CSV` env var. If
neither the configured path nor the default `insurance_companies.csv` is
present, falls back to the shipped `insurance_companies.example.csv` so the
UI still renders something (with clearly-placeholder addresses).
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Map our internal product_type → Hebrew סוג קופה strings in the CSV.
PRODUCT_TO_CSV_KEYS: dict[str, list[str]] = {
    "pension":       ["פנסיה"],
    "gemel":         ["גמל", "גמל והשתלמות"],
    "policy":        ["פוליסה"],
    "study_fund":    ["קרן השתלמות", "השתלמות", "גמל והשתלמות"],
    "child_savings": ["חסכון לכל ילד", "קופת גמל"],
}

# Fall-back keys when no product-specific row exists for a company.
GENERIC_FALLBACK_KEYS = ["לכל פעולה", "כל פעולה", "לכל פעולה/ השלמת מסמכים"]

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV = REPO_ROOT / "insurance_companies.csv"
EXAMPLE_CSV = REPO_ROOT / "insurance_companies.example.csv"


def _resolve_csv_path() -> Path:
    env = os.environ.get("SHEMESH_INSURANCE_CSV")
    if env and Path(env).is_file():
        return Path(env)
    if DEFAULT_CSV.is_file():
        return DEFAULT_CSV
    return EXAMPLE_CSV


CSV_PATH = _resolve_csv_path()


@dataclass(frozen=True)
class InsuranceRow:
    phone: str
    company: str
    product_type: str
    email: str


def _load_rows(csv_path: Path | str = CSV_PATH) -> list[InsuranceRow]:
    rows: list[InsuranceRow] = []
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(InsuranceRow(
                phone=(r.get("טלפון") or "").strip(),
                company=(r.get("שם חברה") or "").strip(),
                product_type=(r.get("סוג קופה") or "").strip(),
                email=(r.get("מייל") or "").strip(),
            ))
    return rows


_CACHE: Optional[list[InsuranceRow]] = None


def all_rows() -> list[InsuranceRow]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _load_rows(_resolve_csv_path())
    return _CACHE


def reload_rows() -> None:
    """Force the next all_rows() call to re-read the CSV from disk."""
    global _CACHE
    _CACHE = None


def all_companies() -> list[str]:
    return sorted({r.company for r in all_rows() if r.company})


def emails_for(company: str, product_type: Optional[str]) -> list[str]:
    """Return distinct emails for (company, product_type), with fallback to
    generic 'לכל פעולה' rows if no product-specific match exists."""
    rows = all_rows()
    keys = PRODUCT_TO_CSV_KEYS.get(product_type or "", []) if product_type else []
    matches: list[InsuranceRow] = []
    for r in rows:
        if r.company != company:
            continue
        if not r.email:
            continue
        if not keys or r.product_type in keys:
            matches.append(r)
    if matches:
        return _unique_preserve_order(r.email for r in matches)
    # Fall back to generic
    fallbacks = [r for r in rows if r.company == company and r.product_type in GENERIC_FALLBACK_KEYS and r.email]
    if fallbacks:
        return _unique_preserve_order(r.email for r in fallbacks)
    # Last resort: any email for this company
    return _unique_preserve_order(r.email for r in rows if r.company == company and r.email)


def _unique_preserve_order(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out
