"""FastAPI app for the Shemesh operation-form workflow.

Routes (all server-rendered Jinja templates):
    GET  /                       upload page
    POST /upload                 process uploads, run extraction + vision, redirect to /review
    GET  /review/{sid}           review extracted ClientPicture (editable)
    POST /review/{sid}           save edits, redirect to /operations
    GET  /operations/{sid}       configure operations
    POST /operations/{sid}       save form, redirect to /preview
    GET  /preview/{sid}          render PDF, run review, show findings
    POST /preview/{sid}/save     persist to SubmissionStore
    GET  /preview/{sid}/pdf      stream the generated PDF
    GET  /submissions            list saved submissions
    GET  /submissions/{sid}/pdf  stream a saved submission's PDF

All steps are designed to be re-enterable — you can always go back to a
previous step and adjust.
"""
from __future__ import annotations

import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..doc_checklist import EmployerReleaseStatus, required_documents
from ..models import (
    AttachedDocuments,
    ClientPicture,
    EmployerLine,
    OperationDetail,
    OperationForm,
    OperationFormCover,
)
from ..render import render_form_to_pdf
from ..review import review_form
from ..rules import apply_tax_recommendation, compute_tax_recommendation
from ..storage import SubmissionStore
from ..unifier import ExtractionInputs, unify
from ..vision import (
    MockVisionExtractor,
    OllamaVisionExtractor,
    OpenAIVisionExtractor,
    VisionExtractor,
)
from .insurance_dir import all_companies, emails_for
from .sessions import Session, store as session_store

log = logging.getLogger("shemesh_ops.web")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        n = session_store.cleanup_old(max_age_seconds=7 * 24 * 3600)
        if n:
            log.info("startup — cleaned up %d expired session folder(s)", n)
    except Exception:
        log.exception("session cleanup failed (non-fatal)")
    yield


app = FastAPI(title="Shemesh – טופס תפעול", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Upload size limit (per file): 10 MB. Real bank PDFs are ~150KB, ID JPEGs ~200KB.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_PDF_TYPES = {"application/pdf", "application/x-pdf"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


def get_vision() -> Optional[VisionExtractor]:
    """Resolve a VisionExtractor based on SHEMESH_VISION env
    (mock | ollama | openai | none)."""
    backend = os.environ.get("SHEMESH_VISION", "mock").lower()
    if backend == "none":
        return None
    if backend == "ollama":
        return OllamaVisionExtractor()
    if backend == "openai":
        return OpenAIVisionExtractor()
    return MockVisionExtractor()


# ---------------------------------------------------------------------------
# Helpers

def _save_upload(upload: UploadFile, dest: Path) -> int:
    """Stream an UploadFile to disk with a size cap. Returns bytes written."""
    total = 0
    with open(dest, "wb") as out:
        while True:
            chunk = upload.file.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"קובץ {upload.filename} גדול מהמותר ({MAX_UPLOAD_BYTES // 1024 // 1024} מגה)",
                )
            out.write(chunk)
    return total


def _validate_filetype(upload: UploadFile, allowed: set[str]) -> None:
    if upload.content_type and upload.content_type.lower() not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"סוג קובץ לא נתמך עבור {upload.filename}: {upload.content_type}",
        )


def _validate_magic_bytes(path: Path, expected_pdf: bool) -> None:
    """Sniff the first few bytes of an uploaded file to catch type spoofing."""
    with open(path, "rb") as f:
        header = f.read(8)
    if expected_pdf and not header.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail=f"קובץ {path.name} אינו PDF תקין (תוכן לא תואם לסיומת)",
        )
    if not expected_pdf:
        # JPEG starts with FFD8FF, PNG with 89504E47, WebP RIFF....WEBP
        if not (header.startswith(b"\xff\xd8\xff") or header.startswith(b"\x89PNG")
                or (len(header) >= 4 and header[:4] == b"RIFF")):
            raise HTTPException(
                status_code=400,
                detail=f"קובץ {path.name} אינו תמונה תקינה (JPEG/PNG/WebP)",
            )


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        try:
            return datetime.strptime(s, "%d/%m/%Y").date()
        except ValueError:
            return None


def _parse_decimal(s: Optional[str]) -> Optional[Decimal]:
    if not s:
        return None
    try:
        return Decimal(s.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _get_session_or_404(sid: str) -> Session:
    try:
        return session_store.get(sid)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"לא נמצאה הגשה פעילה עם המזהה {sid!r}. ייתכן והשרת אותחל — התחל הגשה חדשה.",
        )


def _ensure_picture(session: Session) -> ClientPicture:
    if session.picture is None:
        raise HTTPException(status_code=400, detail="חסר מידע — חזור לשלב 1 והעלה את המסמכים")
    return session.picture


def _ensure_form(session: Session) -> OperationForm:
    if session.form is None:
        # Bootstrap a blank form with no operations
        pic = _ensure_picture(session)
        session.form = OperationForm(
            cover=OperationFormCover(
                form_date=date.today(),
                client_id=pic.identity.id_number,
                client_first_name=(pic.id_card.first_name if pic.id_card else "") or "",
                client_last_name=(pic.id_card.last_name if pic.id_card else "") or "",
                client_date_of_birth=(pic.id_card.date_of_birth if pic.id_card else None),
                client_city=_city_from_address(pic.bank.address) if pic.bank.address else "",
            ),
            operations=[],
        )
    return session.form


def _city_from_address(addr: str) -> str:
    # Best-effort: last comma-separated chunk, or last whitespace-token.
    if "," in addr:
        return addr.split(",")[-1].strip()
    return addr.split()[-1] if addr.split() else ""


# ---------------------------------------------------------------------------
# Routes — step 1: upload


@app.get("/", response_class=HTMLResponse)
async def upload_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "upload.html",
        {"step": 1, "session_id": None},
    )


@app.post("/upload")
async def upload_submit(
    request: Request,
    id_front: UploadFile = File(...),
    id_back: UploadFile = File(...),
    bank: UploadFile = File(...),
    tagmulim: UploadFile = File(...),
    pitsuyim: UploadFile = File(...),
    maslaka: UploadFile = File(None),
    bl_history: UploadFile = File(None),
) -> RedirectResponse:
    s = session_store.new()
    log.info("session %s — new upload", s.id)

    # Bank confirmations sometimes arrive as photos/screenshots — accept both.
    pdf_or_image = ALLOWED_PDF_TYPES | ALLOWED_IMAGE_TYPES
    incoming = {
        "id_front":   (id_front,  ALLOWED_IMAGE_TYPES),
        "id_back":    (id_back,   ALLOWED_IMAGE_TYPES),
        "bank":       (bank,      pdf_or_image),
        "tagmulim":   (tagmulim,  ALLOWED_PDF_TYPES),
        "pitsuyim":   (pitsuyim,  ALLOWED_PDF_TYPES),
        "maslaka":    (maslaka,   ALLOWED_PDF_TYPES),
        "bl_history": (bl_history, ALLOWED_PDF_TYPES),
    }

    for name, (upload, allowed) in incoming.items():
        if upload is None or upload.filename in (None, ""):
            continue
        _validate_filetype(upload, allowed)
        suffix = Path(upload.filename or name).suffix or (".pdf" if "pdf" in (upload.content_type or "") else ".bin")
        dest = s.upload_dir / f"{name}{suffix}"
        size = _save_upload(upload, dest)
        # Detect whether the file is actually a PDF based on extension/header.
        is_pdf = suffix.lower() == ".pdf" or "pdf" in (upload.content_type or "").lower()
        _validate_magic_bytes(dest, expected_pdf=is_pdf)
        log.info("session %s — saved %s (%d bytes) → %s", s.id, name, size, dest.name)
        s.uploads[name] = dest

    inputs = ExtractionInputs(
        bank=s.uploads.get("bank"),
        tagmulim=s.uploads.get("tagmulim"),
        pitsuyim=s.uploads.get("pitsuyim"),
        maslaka=s.uploads.get("maslaka"),
        bl_history=s.uploads.get("bl_history"),
        id_front=s.uploads.get("id_front"),
        id_back=s.uploads.get("id_back"),
    )

    try:
        result = unify(inputs, vision=get_vision())
    except Exception as e:
        log.exception("session %s — extraction failed", s.id)
        raise HTTPException(
            status_code=400,
            detail=f"שגיאה בחילוץ המידע: {e}",
        )

    s.picture = result.picture
    log.info("session %s — extracted picture for client %s", s.id, s.picture.identity.id_number)
    return RedirectResponse(f"/review/{s.id}", status_code=303)


# ---------------------------------------------------------------------------
# Routes — step 2: review


@app.get("/review/{sid}", response_class=HTMLResponse)
async def review_page(request: Request, sid: str) -> HTMLResponse:
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    return templates.TemplateResponse(
        request, "review.html",
        {
            "step": 2, "session_id": sid,
            "picture": pic,
        },
    )


@app.post("/review/{sid}")
async def review_submit(
    sid: str,
    full_name: str = Form(""),
    id_number: str = Form(""),
    holder_name: str = Form(""),
    bank_code: str = Form(""),
    bank_name: str = Form(""),
    branch: str = Form(""),
    account_number: str = Form(""),
    iban: str = Form(""),
    address: str = Form(""),
    phone: str = Form(""),
) -> RedirectResponse:
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    if full_name:
        pic.identity.full_name = full_name
    if id_number:
        pic.identity.id_number = id_number
    if pic.bank:
        pic.bank.holder_name = holder_name or pic.bank.holder_name
        pic.bank.bank_code = bank_code or pic.bank.bank_code
        pic.bank.bank_name = bank_name or pic.bank.bank_name
        pic.bank.branch = branch or pic.bank.branch
        pic.bank.account_number = account_number or pic.bank.account_number
        pic.bank.iban = iban or pic.bank.iban
        pic.bank.address = address or pic.bank.address
    # Stash phone in the form cover (carried into op-config step)
    f = _ensure_form(s)
    f.cover.client_phone = phone or f.cover.client_phone
    log.info("session %s — review saved", sid)
    return RedirectResponse(f"/operations/{sid}", status_code=303)


# ---------------------------------------------------------------------------
# Routes — step 3: operations


@app.get("/operations/{sid}", response_class=HTMLResponse)
async def operations_page(request: Request, sid: str) -> HTMLResponse:
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    form = _ensure_form(s)

    # Pre-compute tax recommendations + required-docs per op for the UI to render
    recommendations = []
    checklists = []
    for op in form.operations:
        recommendations.append(compute_tax_recommendation(pic, op))
        emp_status = [
            EmployerReleaseStatus(
                employer_name=e.employer_name,
                has_161=False, has_funds_release=False,
            )
            for e in op.employers
        ]
        checklists.append(required_documents(op, pic, employer_release=emp_status))

    return templates.TemplateResponse(
        request, "operations.html",
        {
            "step": 3, "session_id": sid,
            "picture": pic,
            "form": form,
            "companies": all_companies(),
            "available_funds": pic.maslaka.funds if pic.maslaka else [],
            "available_employers": pic.pitsuyim.rows if pic.pitsuyim else [],
            "recommendations": recommendations,
            "checklists": checklists,
        },
    )


def _apply_form_post_to_state(fd, pic: ClientPicture, form: OperationForm) -> None:
    """Update `form` in-place from the POST FormData. Shared by every
    operations-page action endpoint so the rep's in-progress edits aren't
    lost when they click add/remove/autofill."""
    form.cover.rep_name = (fd.get("rep_name") or "").strip()
    form.cover.amount_total = _parse_decimal(fd.get("amount_total"))
    form.cover.amount_collected = _parse_decimal(fd.get("amount_collected"))
    pm = fd.get("payment_method") or None
    form.cover.payment_method = pm if pm in {"credit", "bank_transfer", "bit", "cash"} else None
    form.cover.notes = (fd.get("cover_notes") or "").strip()
    form.cover.pull_retzef_from_bituach_leumi = fd.get("pull_retzef") == "on"
    form.cover.pull_for_debt_closure = fd.get("pull_debt") == "on"

    a = AttachedDocuments()
    for field_name in AttachedDocuments.model_fields:
        setattr(a, field_name, fd.get(f"attached_{field_name}") == "on")
    form.cover.attached = a

    op_count = int(fd.get("op_count") or "0")
    new_ops: list[OperationDetail] = []
    for i in range(op_count):
        prefix = f"op_{i}_"
        company = (fd.get(prefix + "company") or "").strip()
        product_type = fd.get(prefix + "product_type") or None
        kupa_number = (fd.get(prefix + "kupa") or "").strip()
        kupa_vintage = _parse_date(fd.get(prefix + "vintage"))
        money_types = []
        if fd.get(prefix + "money_tagmulim") == "on":
            money_types.append("tagmulim")
        if fd.get(prefix + "money_pitsuyim") == "on":
            money_types.append("pitsuyim")
        tax_mode = fd.get(prefix + "tax_mode") or None
        notes = (fd.get(prefix + "notes") or "").strip()

        if product_type not in {"pension", "gemel", "policy", "study_fund", "child_savings"}:
            product_type = None
        if tax_mode not in {"full", "partial", "exempt"}:
            tax_mode = None

        employers: list[EmployerLine] = []
        for j in range(12):
            eprefix = f"{prefix}emp_{j}_"
            name = (fd.get(eprefix + "name") or "").strip()
            if not name:
                continue
            emp_tax = fd.get(eprefix + "tax_mode") or None
            if emp_tax not in {"full", "partial", "exempt"}:
                emp_tax = None
            employers.append(EmployerLine(
                employer_name=name,
                tax_mode=emp_tax,
                tagmulim_full=fd.get(eprefix + "tag_full") == "on",
                tagmulim_amount=_parse_decimal(fd.get(eprefix + "tag_amount")),
                pitsuyim_full_tax=fd.get(eprefix + "pit_full_tax") == "on",
                pitsuyim_tax_exempt=fd.get(eprefix + "pit_exempt") == "on",
            ))

        op = OperationDetail(
            insurance_company=company, product_type=product_type,
            kupa_number=kupa_number, kupa_vintage=kupa_vintage,
            money_types=money_types, tax_mode=tax_mode,
            employers=employers, notes=notes,
        )
        rec = compute_tax_recommendation(pic, op)
        apply_tax_recommendation(op, rec)
        new_ops.append(op)

    form.operations = new_ops


@app.post("/operations/{sid}")
async def operations_submit(request: Request, sid: str) -> RedirectResponse:
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    form = _ensure_form(s)
    fd = await request.form()
    _apply_form_post_to_state(fd, pic, form)
    log.info("session %s — saved %d operations", sid, len(form.operations))
    return RedirectResponse(f"/preview/{sid}", status_code=303)


@app.post("/operations/{sid}/add")
async def operations_add(request: Request, sid: str) -> RedirectResponse:
    """Add an empty פעולה row. Persists any in-progress edits first."""
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    form = _ensure_form(s)
    fd = await request.form()
    if fd.get("op_count") is not None:
        _apply_form_post_to_state(fd, pic, form)
    if len(form.operations) < form.max_operations:
        form.operations.append(OperationDetail())
    return RedirectResponse(f"/operations/{sid}", status_code=303)


@app.post("/operations/{sid}/remove/{idx}")
async def operations_remove(request: Request, sid: str, idx: int) -> RedirectResponse:
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    form = _ensure_form(s)
    fd = await request.form()
    if fd.get("op_count") is not None:
        _apply_form_post_to_state(fd, pic, form)
    if 0 <= idx < len(form.operations):
        form.operations.pop(idx)
    return RedirectResponse(f"/operations/{sid}", status_code=303)


@app.post("/operations/{sid}/autofill-employers/{idx}")
async def operations_autofill_employers(request: Request, sid: str, idx: int) -> RedirectResponse:
    """For פיצויים operations, pre-populate the employer rows from the
    pitsuyim report. Filter to the same kupa (tik_nikuim) when known.
    Persists in-progress form edits first."""
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    form = _ensure_form(s)
    fd = await request.form()
    if fd.get("op_count") is not None:
        _apply_form_post_to_state(fd, pic, form)
    if idx < 0 or idx >= len(form.operations):
        raise HTTPException(status_code=400, detail="פעולה לא קיימת")
    op = form.operations[idx]
    if not pic.pitsuyim:
        raise HTTPException(status_code=400, detail="אין דוח פיצויים בהגשה הזו")

    # Identify the source-fund's tik_nikuim from the maslaka, then filter
    # pitsuyim rows to that tik. Fall back to all rows if we can't.
    target_tik = None
    if pic.maslaka and op.kupa_number:
        for f in pic.maslaka.funds:
            if f.policy_number == op.kupa_number:
                target_tik = f.tik_nikuim
                break

    rows = [
        r for r in pic.pitsuyim.rows
        if (target_tik is None or r.tik_nikuim == target_tik)
        and r.employer_name
        and r.shavi_pitsuyim_per_employer > 0
    ]

    from ..models import EmployerLine
    op.employers = [
        EmployerLine(
            employer_name=r.employer_name,
            pitsuyim_full_tax=True,  # default; rep can flip to פטור
            tagmulim_amount=None,
        )
        for r in rows
    ]
    log.info("session %s op %d — autofilled %d employer(s) from pitsuyim", sid, idx, len(op.employers))
    return RedirectResponse(f"/operations/{sid}", status_code=303)


# ---------------------------------------------------------------------------
# Routes — step 4: preview + review + save


def _render_to_session_pdf(s: Session) -> Path:
    pic = _ensure_picture(s)
    form = _ensure_form(s)
    pdf_path = s.upload_dir / "form.pdf"
    render_form_to_pdf(form, pic, pdf_path)
    s.pdf_path = pdf_path
    return pdf_path


@app.get("/preview/{sid}", response_class=HTMLResponse)
async def preview_page(request: Request, sid: str) -> HTMLResponse:
    from ..vision.base import pdf_page_count
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    form = _ensure_form(s)
    pdf_path = _render_to_session_pdf(s)
    review = review_form(pic, form, str(pdf_path), get_vision())
    page_count = pdf_page_count(pdf_path)

    # Build email-routing suggestions per operation
    routing: list[dict] = []
    for op in form.operations:
        if not op.insurance_company:
            continue
        emails = emails_for(op.insurance_company, op.product_type)
        routing.append({
            "company": op.insurance_company,
            "product_type": op.product_type,
            "emails": emails,
        })

    return templates.TemplateResponse(
        request, "preview.html",
        {
            "step": 4, "session_id": sid,
            "picture": pic,
            "form": form,
            "review_findings": review.findings,
            "block_render": review.block_render(),
            "routing": routing,
            "page_count": page_count,
        },
    )


@app.get("/preview/{sid}/pdf")
async def preview_pdf(sid: str) -> FileResponse:
    s = _get_session_or_404(sid)
    if not s.pdf_path or not s.pdf_path.exists():
        _render_to_session_pdf(s)
    return FileResponse(s.pdf_path, media_type="application/pdf", filename="טופס-תפעול.pdf")


@app.get("/preview/{sid}/page-{n}.png")
async def preview_page_png(sid: str, n: int) -> FileResponse:
    """Render the Nth page of the form PDF as PNG — fallback for browsers
    that don't render embedded PDFs (notably headless Chromium and some
    mobile browsers)."""
    from ..vision.base import render_pdf_pages, pdf_page_count
    s = _get_session_or_404(sid)
    if not s.pdf_path or not s.pdf_path.exists():
        _render_to_session_pdf(s)
    png_path = s.upload_dir / f"page-{n}.png"
    if (not png_path.exists()
            or png_path.stat().st_mtime < s.pdf_path.stat().st_mtime):
        total = pdf_page_count(s.pdf_path)
        if n < 1 or n > total:
            raise HTTPException(status_code=404, detail=f"דף {n} לא קיים בטופס")
        png_bytes = render_pdf_pages(s.pdf_path, [n - 1], dpi=120)[0]
        png_path.write_bytes(png_bytes)
    return FileResponse(png_path, media_type="image/png")


@app.get("/preview/{sid}/page-count")
async def preview_page_count(sid: str) -> dict:
    from ..vision.base import pdf_page_count
    s = _get_session_or_404(sid)
    if not s.pdf_path or not s.pdf_path.exists():
        _render_to_session_pdf(s)
    return {"pages": pdf_page_count(s.pdf_path)}


@app.post("/preview/{sid}/save")
async def preview_save(sid: str) -> RedirectResponse:
    s = _get_session_or_404(sid)
    pic = _ensure_picture(s)
    form = _ensure_form(s)
    pdf_path = _render_to_session_pdf(s)
    review = review_form(pic, form, str(pdf_path), get_vision())
    if review.block_render():
        # Re-render the preview so the user can see the errors
        return RedirectResponse(f"/preview/{sid}", status_code=303)
    store = SubmissionStore()
    sub_id = store.save(
        form, pic, pdf_path=pdf_path,
        review_findings=review.findings, status="reviewed",
    )
    log.info("session %s — saved as submission #%d", sid, sub_id)
    return RedirectResponse(f"/submissions?last={sub_id}", status_code=303)


# ---------------------------------------------------------------------------
# Health check + utility


@app.post("/reset/{sid}")
async def reset_session(sid: str) -> RedirectResponse:
    """Discard the in-flight session (uploads + extracted data + draft form)."""
    session_store.delete(sid)
    log.info("session %s — deleted by reset", sid)
    return RedirectResponse("/", status_code=303)


@app.get("/health")
async def health() -> dict:
    """Quick health probe for deployment monitoring."""
    return {
        "status": "ok",
        "vision_backend": os.environ.get("SHEMESH_VISION", "mock"),
        "active_sessions": len(session_store._sessions),
    }


# ---------------------------------------------------------------------------
# Submissions list


@app.get("/submissions", response_class=HTMLResponse)
async def submissions_page(request: Request, last: Optional[int] = None) -> HTMLResponse:
    store = SubmissionStore()
    rows = store.list_all(limit=100)
    return templates.TemplateResponse(
        request, "submissions.html",
        {
            "step": None,
            "session_id": None,
            "rows": rows,
            "last_id": last,
        },
    )


@app.get("/submissions/{sub_id}/pdf")
async def submission_pdf(sub_id: int) -> FileResponse:
    store = SubmissionStore()
    row = store.get(sub_id)
    if not row or not row.get("pdf_path"):
        raise HTTPException(status_code=404, detail="לא נמצא PDF להגשה")
    p = Path(row["pdf_path"])
    if not p.exists():
        raise HTTPException(status_code=404, detail="קובץ ה-PDF אינו זמין על הדיסק")
    return FileResponse(p, media_type="application/pdf", filename=f"submission-{sub_id}.pdf")


# ---------------------------------------------------------------------------
# Error handler — turn 4xx/5xx into friendly HTML pages


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "error.html",
        {"step": None, "session_id": None,
         "status_code": exc.status_code,
         "detail": exc.detail},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
    log.exception("unhandled exception")
    return templates.TemplateResponse(
        request, "error.html",
        {"step": None, "session_id": None,
         "status_code": 500,
         "detail": f"שגיאה כללית: {exc}",
         "trace": traceback.format_exc()},
        status_code=500,
    )
