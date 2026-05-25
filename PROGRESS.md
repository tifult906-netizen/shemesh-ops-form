# Progress notes

## How to try it

```bash
cd ~/projects/shemesh-ops-form
python -m shemesh_ops.web
# → http://127.0.0.1:8000
```

You'll need to supply your own client documents (5 PDFs + 2 ID photos) —
the repo does not ship with any example fixtures.

## What was built

### Web UI (FastAPI, server-rendered Jinja, Hebrew RTL)

4-step workflow with persistent nav and "התחל מחדש" / "הגשות שמורות" links:

1. **Upload** — 7 file inputs, size+magic-byte validation, friendly Hebrew error pages.
2. **Review** — editable client identity + bank + read-only summary of ID card / extracted funds / extracted employers.
3. **Operations** — add/remove up to 6 פעולה rows; per row select company (18-option dropdown), product, kupa (dropdown of the maslaka funds with balance shown), money types (תגמולים/פיצויים checkboxes), tax mode (auto-locked when rules say so, with reason shown), employer rows with datalist autocomplete. "⤵ טען מעסיקים מדוח פיצויים" button pre-fills employers from the pitsuyim report. Required-docs checklist surfaced live per פעולה.
4. **Preview** — PNG previews of every page (works in every browser, including headless), download link, save button. Model-review findings shown with severity colors; save blocked on errors. Email-routing suggestions per פעולה with one-click mailto: links.

Plus a **submissions list** at /submissions with PDF download per row.

### Hardening

- File-upload size cap (10 MB) + content-type whitelist + magic-byte sniffing (rejects spoofed files)
- Unifier wraps every parser + vision call in graceful try/except — a single failure surfaces as a note
- Friendly Hebrew error pages instead of 500 stack traces
- `/health` probe endpoint for monitoring
- Startup hook cleans up session folders older than 7 days
- Session-mutating endpoints persist in-progress form edits FIRST before doing their action

### Tests

28 tests covering pure logic (rules, doc checklist, review with synthetic
ClientPicture, storage). The fixture-dependent tests (parsers, unifier,
renderer, web pipeline) were removed when the example client PDFs were
removed for privacy — they can be re-added against your own fixtures.

### Configuration env vars

- `SHEMESH_HOST`, `SHEMESH_PORT`, `SHEMESH_VISION`, `SHEMESH_VISION_MODEL`
- `SHEMESH_DB`, `SHEMESH_SESSION_ROOT`
- `SHEMESH_FONT_PATH`, `SHEMESH_FONT_BOLD_PATH`
- `OLLAMA_HOST`

## Privacy note

This repo intentionally ships with **zero client data**. The MockVisionExtractor
returns generic placeholders ("ישראל ישראלי", "999999999", "מעסיק דוגמה א" etc).
For real usage, point the app at OllamaVisionExtractor with a local model and
process your actual client documents on your own machine.

## Things explicitly not done

- **Auth** — the web app trusts whoever can reach the port. Real prod needs Cloudflare Tunnel + access policy, or a reverse proxy with auth.
- **Multi-tenancy** — single SQLite, single in-memory session map.
- **Real email send** — only suggested recipients + mailto: links are surfaced. Browsers don't let mailto attach files, so the rep manually attaches the downloaded PDF.
- **OllamaVisionExtractor** prompts are sensible defaults but haven't been load-tested. Will likely need tuning when you point it at the first real client.

## Known UX limitations

- PDF preview in browser uses PNG fallback plus an `embed` (the embed only works in browsers with PDF viewers; PNGs work everywhere).
- Operations form doesn't have inline JS validation — server-side review catches errors after submit.
