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
