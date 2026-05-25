# Shemesh – טופס תפעול

Hebrew-RTL web tool that turns a client's source documents into a filled-in **internal operation form** (טופס תפעול) for the sales rep's own records.

The rep uploads 5 PDFs + 2 ID photos. The system extracts everything (numeric fields deterministically, Hebrew labels via a local vision model), runs the relevant tax + document-checklist rules, and produces a Hebrew RTL PDF matching the standard internal template. The actual per-company withdrawal forms are a future addition — for now this tool's only job is to deliver that one summary PDF to the rep.

## What it does end-to-end

1. **Upload** — תעודת זהות (front + back), אישור ניהול חשבון, דוח יתרות תגמולים, דוח יתרות פיצויים, דוח מסלקה, אישור תקופות ביטוח ומעסיקים.
2. **Extract** — every PDF parsed deterministically for numbers/IDs/dates; Hebrew labels filled via a vision pass (mock or local Ollama model).
3. **Review** — rep validates the extracted ClientPicture (every field editable).
4. **Configure operations** — rep adds up to 6 פעולה rows: company × product × kupa × תגמולים/פיצויים × per-employer breakdown.
5. **Auto-rules apply**:
   - **Tax mode**: הוני bucket auto-locks to פטור; קה"ש ≥6 yrs → exempt; <6 yrs → 35% (with cross-fund vintage-override surface).
   - **Required docs**: deterministic checklist by money type, client age, employer 161/release status, Altshuler/Harel 2-year rule.
6. **Model review** — deterministic checks (ID consistency, dates, amounts, kupa-exists) + optional LLM sanity-check on the rendered form. Errors block save; warnings need rep ack.
7. **Render + save** — Hebrew RTL PDF matching the internal layout (pymupdf direct draw + python-bidi), stored in SQLite alongside the source ClientPicture.

> **Out of scope for now:** filling the per-company withdrawal forms (e.g. מגדל's
> own pidyon form, הראל's, etc.). That's a separate phase. The
> `insurance_companies.csv` mapping ships with this repo as input for that
> future work, but the current pipeline doesn't email or auto-submit anything.

## Install

**For non-developers (recommended):** open the interactive setup page —
detects your OS, gives you a one-shot installer command or a step-by-step
checklist with copy-able commands and direct download links:

→ **https://tifult906-netizen.github.io/shemesh-ops-form/presentation/setup.html**

**One-shot installer** (Windows): the most reliable path is to **download
the script as a file and right-click → Run with PowerShell** — that
sidesteps every terminal-paste / line-wrap quirk:

→ https://tifult906-netizen.github.io/shemesh-ops-form/scripts/setup-windows.ps1

If you prefer to paste into an already-open PowerShell (run as Admin),
use 4 lines — each is a complete statement so terminal line-wrapping
can't break the middle:

```powershell
$u='https://tifult906-netizen.github.io/shemesh-ops-form/scripts/setup-windows.ps1'
[Net.ServicePointManager]::SecurityProtocol='Tls12'
$wc=New-Object Net.WebClient; $wc.Encoding=[System.Text.Encoding]::UTF8
iex $wc.DownloadString($u)
```

> Three gotchas to know about (all fixed by the above):
> (1) GitHub Pages serves `.ps1` as `application/octet-stream`, so `iwr`
> returns the body as `byte[]` and `iex` can't parse bytes. Use
> `Net.WebClient.DownloadString` which returns a string.
> (2) `DownloadString` defaults to the system codepage (CP1252 on most
> Windows). If the script has any non-ASCII chars (em-dash, hebrew, etc.)
> they get mojibaked. Setting `$wc.Encoding=[System.Text.Encoding]::UTF8`
> fixes this. The script itself is now pure ASCII as defense-in-depth.
> (3) The classic Windows console (conhost) splits pasted text at the
> terminal width (~70 cols), breaking long one-liners mid-expression.
> Multi-line where each line is a complete statement avoids that.

macOS / Linux equivalent:

```bash
curl -fsSL https://tifult906-netizen.github.io/shemesh-ops-form/scripts/setup-mac.sh | bash
```

**Manual install** (if you already have Python 3.11+):

```bash
git clone https://github.com/tifult906-netizen/shemesh-ops-form
cd shemesh-ops-form
python -m venv .venv
.venv\Scripts\activate                # Windows PowerShell
# or: source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
pip install -e .
```

Python ≥ 3.11. Pure-Python except for one optional system dependency: a Hebrew TTF font for PDF rendering.

### Hebrew font

Set `SHEMESH_FONT_PATH` to any TTF that includes Hebrew glyphs.
- **Windows** (default): `C:/Windows/Fonts/arial.ttf` is auto-detected.
- **Linux/Mac**: download Noto Sans Hebrew or use DejaVu Sans:
  ```bash
  export SHEMESH_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
  ```

## Run

### Web UI (the main thing)

```bash
python -m shemesh_ops.web
# → http://127.0.0.1:8000
```

Or with uvicorn directly (gives you `--reload`, multiple workers, etc.):

```bash
uvicorn shemesh_ops.web.app:app --host 127.0.0.1 --port 8000 --reload
```

Then open `http://127.0.0.1:8000` in the browser and walk through the 4 steps.

Configuration env vars:
- `SHEMESH_HOST`, `SHEMESH_PORT` — bind address (default 127.0.0.1:8000)
- `SHEMESH_VISION` — `mock` | `ollama` | `none` (default `mock`)
- `SHEMESH_VISION_MODEL` — Ollama model tag (default `qwen2.5vl:7b`)
- `SHEMESH_DB` — SQLite path (default `~/.shemesh-ops/submissions.db`)
- `SHEMESH_SESSION_ROOT` — upload session dir (default `~/.shemesh-ops/sessions`)
- `SHEMESH_FONT_PATH`, `SHEMESH_FONT_BOLD_PATH` — Hebrew font TTF paths
- `SHEMESH_INSURANCE_CSV` — override path to the company × email lookup CSV
  (defaults to `insurance_companies.csv` at the repo root; the shipped one
  contains public OSINT addresses for 18 Israeli insurance companies)
- `OLLAMA_HOST` — Ollama daemon URL (default `http://localhost:11434`)

### CLI

For headless/scripted use:

```bash
python -m shemesh_ops.cli \
    --scan-dir ./fixtures \
    --vision mock \
    --apply-tax-rules \
    --render-form out.pdf \
    --review \
    --save
```

Flags:
- `--scan-dir <path>` — auto-find default-named files in directory
- `--vision none|mock|ollama` (default `mock`)
- `--apply-tax-rules` — run tax-mode rules + write reasons to stderr
- `--render-form <path>` — render the example operation form to this PDF
- `--review` — run the model-review gate (blocks render if errors)
- `--save` — persist to SQLite

JSON of the unified ClientPicture is written to stdout; status messages to stderr.

## Vision-model setup (real local inference)

The mock vision extractor only returns canned values for the example customer (ישראל ישראלי). For real clients you need a local vision model:

### Option 1: Ollama (recommended)

```bash
# Install Ollama: https://ollama.com/download
ollama pull qwen2.5vl:7b           # good Hebrew support, ~5GB
# or:
ollama pull llama3.2-vision:11b    # alternative, ~8GB
```

Then point the app at it:

```bash
export SHEMESH_VISION=ollama
export SHEMESH_VISION_MODEL=qwen2.5vl:7b
export OLLAMA_HOST=http://localhost:11434
```

### Option 2: Don't use vision

```bash
export SHEMESH_VISION=none
```

The pipeline will still produce a PDF; Hebrew labels for kupa names, employer names, and ID-card data will be blank or have to be entered manually in the review step.

## Project layout

```
src/shemesh_ops/
├── models.py                # Pydantic types (ClientPicture, OperationForm, ...)
├── parsers/                 # PDF parsers (deterministic, no LLM)
│   ├── bank.py
│   ├── tagmulim.py
│   ├── pitsuyim.py
│   ├── maslaka.py
│   └── bl_history.py
├── vision/                  # Vision extractors (LLM-backed)
│   ├── base.py              # VisionExtractor ABC
│   ├── mock.py              # canned synthetic responses (no real data)
│   ├── ollama_backend.py    # real local inference
│   └── extractors.py        # high-level helpers (ID card, label-fill)
├── unifier.py               # Combine 5 parsers → ClientPicture, cross-refs
├── rules.py                 # Tax-mode auto-lock + קה"ש 6-year rule
├── doc_checklist.py         # Required-documents engine
├── render/                  # Hebrew RTL PDF rendering
│   ├── renderer.py          # pymupdf direct draw + python-bidi
│   └── form_builder.py      # builds example OperationForm
├── review.py                # Model-review gate (deterministic + LLM)
├── storage.py               # SQLite submission store
├── cli.py                   # Headless CLI
└── web/                     # FastAPI web UI
    ├── app.py               # routes
    ├── sessions.py          # in-flight session state
    ├── insurance_dir.py     # CSV company→email lookup
    ├── templates/           # Jinja2 RTL templates
    └── static/style.css     # RTL CSS

tests/                       # 50 tests, deterministic
UNDERSTANDING.md             # canonical spec
insurance_companies.csv      # 18 companies × per-product emails
```

## Tests

```bash
python -m pytest
```

The tests covering pure logic (rules, doc checklist, review, storage,
synthetic ClientPicture construction) run without any fixture files.

Tests covering PDF parsing, the unifier, the renderer, and the web UI
require local fixture PDFs that are not committed to the repo for
privacy reasons. To re-enable those, drop a customer's 5 source PDFs +
2 ID photos into `tests/fixtures/<customer_name>/` and write a small
conftest that points the existing tests at that directory.

## Architecture decisions worth knowing

1. **Hebrew text-layer extraction fails on every financial PDF** — they use custom CID-mapped subset fonts. Numeric/Latin fields extract cleanly; Hebrew labels need vision. The parsers leave Hebrew slots as `""` for the vision pass to fill.

2. **PDF rendering uses pymupdf + python-bidi, not HTML→PDF.** WeasyPrint requires GTK runtime which doesn't install cleanly on Windows. xhtml2pdf can't load Hebrew TTFs in a sandboxed env. Direct draw is more code but Just Works on Windows out of the box.

3. **All deterministic logic is pure functions** — `rules.compute_tax_recommendation`, `doc_checklist.required_documents`, `review.deterministic_review` all take a `ClientPicture` + `OperationForm` and return a value with no side effects. Unit tests cover every branch.

4. **The vision interface is provider-agnostic.** Swapping models = implementing one method on `VisionExtractor`. The Mock backend exists so the test suite is deterministic and CI doesn't need a GPU.

5. **Sessions are filesystem-backed**, indexed in-memory. Single-process for now; for multi-process scale, swap `SessionStore` for Redis.

## Known limitations / next-up

- **Vision-fill of Hebrew labels in OllamaVisionExtractor needs tuning** against a real client — prompts are sensible defaults but not load-tested.
- **No authentication.** The web app trusts whoever can reach it. Add Cloudflare Tunnel + access policy or wrap with a reverse proxy for prod.
- **No multi-tenancy.** SQLite is shared; one rep at a time effectively.
- **PDF preview in browser** uses `<embed>` — works in desktop browsers with PDF viewers; headless Chromium shows blank. Download link always works.
- **Email send is not implemented** — only suggested recipients are surfaced (see `routing` on the preview page). Wire to SMTP/Graph API if needed.

## License & contact

Internal Shemesh tooling.
