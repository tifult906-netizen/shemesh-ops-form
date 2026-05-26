# Security policy

## Reporting a vulnerability

If you find a security issue in this project, please **do not open a public GitHub issue**.

Instead, use GitHub's private vulnerability reporting:
**https://github.com/tifult906-netizen/shemesh-ops-form/security/advisories/new**

We aim to acknowledge reports within 7 days.

## What's in scope

This repo ships:
- a FastAPI web service intended to be run on `127.0.0.1` for a single rep
- deterministic PDF parsers
- a local SQLite store at `~/.shemesh-ops/submissions.db`
- a vision-extractor abstraction with a Mock backend (synthetic values only)
  and an Ollama backend that calls a locally-running daemon

In scope:
- Code-execution paths in the web layer (upload, render, save)
- File-validation bypasses (size, type, magic-bytes)
- Template-injection or XSS in the Jinja2 templates
- Path-traversal in any endpoint that reads from disk
- Anything that lets one rep see another rep's data via the API

Out of scope:
- Issues that require the rep to actively attack themselves (e.g. uploading a
  PDF designed to exploit pdfplumber — that's the rep's own input on their
  own machine)
- Hosting decisions (exposing the app to the public internet without an
  auth layer is documented as dangerous in README.md and is not a project bug)
- Issues in upstream dependencies (file those upstream; we track via
  Dependabot — see `.github/dependabot.yml`)
- The MockVisionExtractor's hardcoded synthetic values

## OpenAI key handling (when `SHEMESH_VISION=openai`)

The OpenAI vision backend trades local-only processing for much higher
Hebrew extraction quality. When this backend is active:

- The web UI shows a red sticky banner on every page: "⚠ מודל ענן פעיל".
- Every uploaded document (ID card photos, bank confirmations, pension
  reports) is base64-encoded and POSTed to `api.openai.com`.
- OpenAI retains API requests for up to **30 days** for abuse monitoring
  (default for non-Enterprise tiers). For Israeli personal-data
  compliance you may need a DPA with OpenAI, client consent, or to
  switch to the local Ollama backend in production.

### Setting up the key (one-time per rep machine)

```powershell
# In each rep's PowerShell, as that user (not Admin):
[Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'sk-...', 'User')
[Environment]::SetEnvironmentVariable('SHEMESH_VISION', 'openai',  'User')
# Close + reopen PowerShell for the new env to take effect.
```

### Usage cap (do this once, on the OpenAI dashboard)

To bound the blast radius if a key leaks:

1. Sign in to https://platform.openai.com/.
2. Settings → Billing → Usage limits.
3. Set a **Hard limit** of $20 / month (well above realistic usage —
   gpt-4o-mini at ~$0.01 per client × ~200 clients/month = $2).
4. Set a **Soft limit** of $10/month so you get an email warning
   before the hard cap blocks all requests.

### When to rotate the key

- **Immediately** if you suspect a leak (key shown on a screenshot,
  committed to git, screen-shared, etc.)
- **Immediately** if a rep leaves the team
- **Quarterly** as routine hygiene (1st of Jan / Apr / Jul / Oct)
- After any laptop loss / theft involving a rep machine

### How to rotate

1. Open https://platform.openai.com/api-keys
2. Click **+ Create new secret key** — name it `shemesh-ops-form-YYYYMM`
3. Copy the new `sk-...` value somewhere temporary
4. Push the new key to each rep's machine (PowerShell as the rep):
   ```powershell
   [Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'sk-NEW...', 'User')
   ```
   Then close + reopen any open PowerShell windows.
5. Back on the dashboard, **revoke the old key** (trash icon next to
   the old `sk-...`). Don't just create the new one — actively kill
   the old one so any leaked copy stops working.
6. Verify: have a rep do a real client extraction. If it succeeds,
   you're done.

### Storing the key safely

- ✅ Windows User-level environment variable (the recommended setup)
- ✅ A password manager (1Password / Bitwarden) for the master copy
- ❌ Never commit to git (`.env` files, scripts, docs)
- ❌ Never paste into Slack/WhatsApp/email
- ❌ Never type into a shared screen
- ❌ Never embed in a `.bat` / `.ps1` file on disk

The repo's `.gitignore` excludes `.env` and the `SECURITY.md` reporting
flow covers credential-leak reporting.

## Data retention

The web app stores two kinds of data on disk:

- **Per-session uploads** in `~/.shemesh-ops/sessions/<id>/` — the raw
  PDFs + ID photos the rep uploaded for an in-progress submission.
  Auto-purged at startup if older than **7 days**.
- **Saved submissions** in `~/.shemesh-ops/submissions.db` (SQLite row)
  + the generated form PDF on disk. Auto-purged at startup if older
  than **90 days** (configurable via `SHEMESH_SUBMISSION_RETENTION_DAYS`).

Both rows AND the referenced PDF files are deleted — there's no
audit-log-only mode. If you need long-term auditing without keeping
client documents, run a periodic export job before the cleanup window.

For an immediate purge of everything, stop the server, delete the two
directories, and restart:

```powershell
Remove-Item -Recurse -Force ~\.shemesh-ops\sessions
Remove-Item -Force ~\.shemesh-ops\submissions.db
```

## Threat model

This tool is designed for a single trusted rep processing client documents on
their own machine. It assumes:

- The rep has physical / OS-level access control on their device
- The web app is bound to `127.0.0.1` (default)
- The vision backend is the Mock (test only) or a locally-running Ollama

If any of those assumptions break, the threat surface expands accordingly —
see README.md "Known limitations" for the relevant caveats.

## Disclosure timeline

For confirmed vulnerabilities:

- We'll publish a fix or mitigation as fast as practical (usually within
  14 days for low/medium severity, faster for high/critical).
- We'll credit the reporter in the release notes unless they prefer otherwise.
- We may publish a GitHub Security Advisory for high-severity issues.
