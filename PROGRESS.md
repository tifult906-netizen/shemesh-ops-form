# Progress today (2026-05-24)

## How to try it

```bash
cd ~/projects/shemesh-ops-form
python -m shemesh_ops.web
# → http://127.0.0.1:8000
```

Walk through: upload the 7 fixture files (from the project root) → review → operations → preview → save.

## What was built today

### Full web UI (FastAPI, server-rendered Jinja, Hebrew RTL)

4-step workflow with persistent nav and "התחל מחדש" / "הגשות שמורות" links:

1. **Upload** — 7 file inputs, size+magic-byte validation, friendly Hebrew error pages on rejection.
2. **Review** — editable client identity + bank + read-only summary of ID card / extracted funds (8) / extracted employers (7). All Hebrew labels filled by the vision pass.
3. **Operations** — add/remove up to 6 פעולה rows; per row select company (18-option dropdown from the CSV), product, kupa (dropdown of the 8 maslaka funds with balance shown), money types (תגמולים/פיצויים checkboxes), tax mode (auto-locked when rules say so, with the reason shown), employer rows with datalist-autocomplete. **"⤵ טען מעסיקים מדוח פיצויים"** button pre-fills employers from the pitsuyim report. Required-docs checklist surfaced live per פעולה.
4. **Preview** — PNG previews of every page (works in every browser, including headless), download link, save button. Model-review findings shown with severity colors; save blocked on errors. Email-routing suggestions per פעולה with one-click mailto: links.

Plus a **submissions list** at /submissions with PDF download per row.

### Hardening

- File-upload size cap (10 MB) + content-type whitelist + **magic-byte sniffing** (rejects spoofed files with the wrong header)
- Unifier wraps every parser + vision call in graceful try/except — a single failure surfaces as a note but doesn't kill the pipeline
- All session_store.get calls now go through a `_get_session_or_404` helper that returns a friendly Hebrew error page
- `/health` probe endpoint for monitoring
- Startup hook cleans up session folders older than 7 days
- All session-mutating endpoints (add op / remove op / autofill employers) now **persist the rep's in-progress form edits first** before doing their action (was a real bug — they were throwing edits away)

### Tests added today

10 new tests, 58 total passing:

- `tests/test_web.py` (10) — full E2E pipeline via TestClient, oversized upload, autofill employers, PNG preview, reset session, health endpoint
- `tests/test_edge_cases.py` (10) — corrupt PDFs, empty PDFs, partial extraction, unifier-with-just-one-input, doc-checklist with no ID card, garbled-ID review flag

### Configuration

All via env vars (see README):

- `SHEMESH_HOST`, `SHEMESH_PORT`, `SHEMESH_VISION`, `SHEMESH_VISION_MODEL`
- `SHEMESH_DB`, `SHEMESH_SESSION_ROOT`
- `SHEMESH_FONT_PATH`, `SHEMESH_FONT_BOLD_PATH`
- `OLLAMA_HOST`

## Sample screenshots taken

Files in `~/`:
- `ui_step1_upload.png` — upload page
- `ui_step2_review.png` — extraction review with all 8 funds + 7 employers
- `ui_step3_top.png`, `ui_step3_with_autofill.png` — operations config
- `ui_step4_top.png` — preview with email routing
- `ui_submissions.png` — submissions list

## What to look at first

1. **README.md** — full setup + architecture overview
2. **UNDERSTANDING.md** — the canonical spec (now finalized — every section validated against working code)
3. **demo_form_output.pdf** — the rendered example operation form
4. **`python -m pytest`** — 58 tests, all green, ~25s on this box

## Things I explicitly didn't do but flagged

- **Auth** — the web app trusts whoever can reach the port. Real prod needs Cloudflare Tunnel + access policy, or a reverse proxy with auth.
- **Multi-tenancy** — single SQLite, single in-memory session map. Fine for one rep at a time; for many concurrent reps, swap SessionStore for Redis.
- **Real email send** — only suggested recipients + mailto: links are surfaced. Browsers don't let mailto attach files, so the rep has to manually attach the downloaded PDF. Wire to SMTP if you want true automation.
- **OllamaVisionExtractor** prompts are sensible defaults but haven't been load-tested against real clients beyond אורי. Will likely need tuning when you point it at the first real client.

## Known UX limitations

- PDF preview in browser uses PNG fallback (works everywhere) plus an `embed` (only works in browsers with PDF viewers). The PNGs are cached on disk per session.
- Operations form doesn't have inline JS validation — server-side review catches errors. Adding inline validation would require JS we deliberately skipped to keep the stack simple.

## Numbers

- 58 tests, 100% pass
- 6 vision-extractor task types (id_card, bank, tagmulim, pitsuyim, maslaka, bl)
- 18 supported insurance companies + per-product email routing
- 8 operation pages (cover + 6 פעולה + room for the rep's edits)
- 5 deterministic PDF parsers
- 1 PDF rendering pipeline (pymupdf + python-bidi, no GTK / wkhtmltopdf binary deps)
- 0 external services required (mock vision works without GPU)
