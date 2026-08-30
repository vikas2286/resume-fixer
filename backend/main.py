"""Resume Fixer - FastAPI backend.

Flow: Upload -> Parse -> Score -> diagnosis -> (rewrite / redflags / jdmatch)
-> generate fixed PDF from template -> re-score -> before/after diff.
"""
from __future__ import annotations

import copy
import os
import sys
import shutil
import tempfile

# Make the backend package directory importable regardless of how uvicorn is
# launched (e.g. `uvicorn main:app` from here vs `uvicorn backend.main:app`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import llm_service
import parser as resume_parser
import scoring
import session_store
import template_engine

app = FastAPI(title="Resume Fixer", version="1.0.0")

# CORS: allowed browser origins.  Set ALLOWED_ORIGINS as a comma-separated
# env var on the host to allow the deployed frontend's domain (e.g.
# "https://resume-fixer.onrender.com").  When unset, the localhost dev
# origins below are used - so local development keeps working unchanged.
_ALLOWED_ORIGINS_ENV = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = ([o.strip() for o in _ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
                   if _ALLOWED_ORIGINS_ENV
                   else ["http://localhost:5173", "http://127.0.0.1:5173",
                         "http://localhost:3000"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXT = {".pdf", ".docx"}
TMP_DIR = os.path.join(tempfile.gettempdir(), "resume_fixer")
os.makedirs(TMP_DIR, exist_ok=True)

# --- "minimal changes needed" thresholds (configurable) ----------------------
# A resume scoring at/above BOTH score floors AND producing fewer than
# MINOR_FIX_MAX_FLAGS red flags does not need the full rebuild flow - the user
# just gets bullet-level wording suggestions instead of a before/after diff.
MINOR_FIX_ATS_MIN = 85      # ATS parseability floor (0-100)
MINOR_FIX_VISUAL_MIN = 90   # visual/recruiter floor (0-100)
# Rule-based red flags are stylistic nitpicks (passive voice, missing metric)
# that even excellent resumes accrue a handful of; the gate exists to catch
# genuinely messy resumes, not to punish 4-5 wording nits on a clean one.
MINOR_FIX_MAX_FLAGS = 6     # minor mode allowed only if len(flags) <= this


def _assess_fix_mode(scores: dict, parsed: dict) -> dict:
    """Decide between 'full fix' mode and 'minor suggestions only' mode."""
    flags = llm_service.rule_based_red_flags(
        resume_parser.structured_to_plain_text(parsed.get("structured") or {})
        or parsed.get("raw_text", ""))
    ats = scores.get("ats", {}).get("score", 0)
    vis = scores.get("visual", {}).get("score", 0)
    clean_structure = (ats >= MINOR_FIX_ATS_MIN and vis >= MINOR_FIX_VISUAL_MIN)
    few_flags = len(flags) <= MINOR_FIX_MAX_FLAGS
    minor_only = clean_structure and few_flags
    # Decision audit trail: shows exactly why a resume landed in each mode.
    print("[fix-mode] ats=%d visual=%d flags=%d "
          "(thresholds ats>=%d visual>=%d flags<=%d) -> %s"
          % (ats, vis, len(flags), MINOR_FIX_ATS_MIN, MINOR_FIX_VISUAL_MIN,
             MINOR_FIX_MAX_FLAGS,
             "MINOR - already well-structured" if minor_only
             else "FULL FIX"), file=sys.stderr)
    if minor_only:
        msg = ("Your resume is already well-structured (ATS %d, Visual %d). "
               "We found %d minor wording improvement%s you could make - "
               "here they are."
               % (ats, vis, len(flags), "" if len(flags) == 1 else "s"))
    else:
        reasons = []
        if not clean_structure:
            reasons.append("structural issues (ATS %d / Visual %d)" % (ats, vis))
        if not few_flags:
            reasons.append("%d content red flags" % len(flags))
        msg = ("This resume needs a full fix: %s." % " and ".join(reasons))
    return {
        "needs_major_fix": not minor_only,
        "mode": "full_fix" if not minor_only else "minor_suggestions",
        "minor_suggestions": flags,
        "message": msg,
        "thresholds": {"ats_min": MINOR_FIX_ATS_MIN,
                       "visual_min": MINOR_FIX_VISUAL_MIN,
                       "max_flags": MINOR_FIX_MAX_FLAGS},
    }


def _session_or_404(sid: str) -> dict:
    s = session_store.get(sid)
    if s is None:
        raise HTTPException(404, "Session not found or expired. Re-upload.")
    return s


def _public_parsed(parsed: dict) -> dict:
    """Trimmed parsed payload for the frontend (no heavy geometry data)."""
    return {
        "file_type": parsed.get("file_type"),
        "n_pages": parsed.get("n_pages"),
        "fonts": parsed.get("fonts"),
        "multicolumn": parsed.get("multicolumn"),
        "has_tables": parsed.get("has_tables"),
        "contact": parsed.get("contact"),
        "sections_found": sorted(
            set((parsed.get("section_titles") or parsed.get("sections") or {}).values())),
        "structured": parsed.get("structured"),
        "preview_text": parsed.get("raw_text", "")[:1500],
    }


# ---------------------------------------------------------------- 1. upload

def _layout_notice(parsed: dict) -> dict:
    """Frontend-facing notice fields: page-preservation plan and the
    multi-column safety warning (we do not reconstruct 2-column layouts)."""
    n_pages = int(parsed.get("n_pages") or 1)
    reason = None
    if n_pages >= 2:
        reason = ("Original content requires multiple pages - the fixed "
                  "PDF keeps ~%d page(s) at full readable font size "
                  "instead of compressing to one." % n_pages)
    layout_warning = None
    if parsed.get("multicolumn_strong"):
        layout_warning = ("Multi-column layout detected - results may be "
                          "incomplete or misordered.")
    return {"original_pages": n_pages, "multi_page_reason": reason,
            "layout_warning": layout_warning}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Unsupported file type. Use PDF or DOCX.")

    in_path = os.path.join(TMP_DIR,
                           "%s_%s" % (os.urandom(6).hex(), file.filename))
    try:
        with open(in_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        parsed = resume_parser.parse_file(in_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            422, "Could not parse this file (%s). Is it a valid %s?"
                 % (e.__class__.__name__, ext.strip(".")))

    scores = scoring.score_resume(parsed)
    assessment = _assess_fix_mode(scores, parsed)
    sid = session_store.create({
        "filename": file.filename,
        "original_path": in_path,
        "parsed": parsed,
        "initial_scores": scores,
        "fix_assessment": assessment,
        "rewritten": False,
    })
    return {
        "session_id": sid,
        "filename": file.filename,
        "parsed": _public_parsed(parsed),
        "scores": scores,
        "needs_major_fix": assessment["needs_major_fix"],
        "fix_mode": assessment["mode"],
        "fix_assessment": assessment,
        "gemini_enabled": llm_service.gemini_available(),
        **_layout_notice(parsed),
    }


# ---------------------------------------------------------------- 2. score

@app.get("/score/{sid}")
def get_score(sid: str):
    s = _session_or_404(sid)
    return {"scores": s["initial_scores"],
            "needs_major_fix": s.get("fix_assessment", {}).get("needs_major_fix", True),
            "fix_mode": s.get("fix_assessment", {}).get("mode", "full_fix"),
            "fix_assessment": s.get("fix_assessment"),
            "parsed": _public_parsed(s["parsed"]),
            **_layout_notice(s["parsed"])}


# ---------------------------------------------------------------- 3. rewrite

@app.post("/rewrite/{sid}")
def rewrite(sid: str):
    s = _session_or_404(sid)
    # Deep-copy so rewritten bullets never mutate the stored original parse.
    structured = copy.deepcopy(s["parsed"].get("structured") or {})
    if not structured:
        raise HTTPException(422, "No structured content to rewrite.")
    if not llm_service.gemini_available():
        raise HTTPException(
            503, "Gemini API key not configured (set GEMINI_API_KEY). "
                 "Rule-based fixes are still available via /generate.")

    context = structured.get("headline", "")
    changed = 0
    for sec in structured.get("sections", []):
        if sec.get("type") != "entries":
            continue
        for entry in sec.get("entries", []):
            bullets = [b for b in entry.get("bullets", []) if b]
            if not bullets:
                continue
            rewrites = llm_service.rewrite_bullets(bullets, context)
            new_bullets = []
            for orig, rw in zip(entry["bullets"], rewrites):
                if rw and rw != orig:
                    changed += 1
                    new_bullets.append(rw)
                else:
                    new_bullets.append(orig)
            entry["bullets"] = new_bullets
    session_store.update(sid, structured_override=structured, rewritten=True)
    return {"ok": True, "bullets_rewritten": changed}


# ---------------------------------------------------------------- 4. redflags

@app.post("/redflags/{sid}")
def redflags(sid: str):
    s = _session_or_404(sid)
    cached = s.get("redflags")
    if cached is None:
        text = (resume_parser.structured_to_plain_text(s["parsed"]["structured"])
                or s["parsed"].get("raw_text", ""))
        cached = llm_service.detect_red_flags(text)
        session_store.update(sid, redflags=cached)
    return {"flags": cached,
            "engine": "gemini" if llm_service.gemini_available() else "rules"}


# ---------------------------------------------------------------- 5. jd match

class JDRequest(BaseModel):
    jd_text: str


@app.post("/jdmatch/{sid}")
def jdmatch(sid: str, body: JDRequest):
    s = _session_or_404(sid)
    if len(body.jd_text.strip()) < 50:
        raise HTTPException(400, "Job description too short - paste the full text.")
    text = (resume_parser.structured_to_plain_text(s["parsed"]["structured"])
            or s["parsed"].get("raw_text", ""))
    return llm_service.match_jd(text, body.jd_text)


# ---------------------------------------------------------------- 6. generate

@app.post("/generate/{sid}")
def generate(sid: str, template: str = "auto"):
    s = _session_or_404(sid)
    structured = s.get("structured_override") or s["parsed"].get("structured")
    if not structured or not structured.get("name"):
        # last-chance LLM structuring before giving up
        try:
            raw = s["parsed"].get("raw_text", "")
            llm_structured = llm_service.structure_resume(raw) if raw else None
        except Exception:  # noqa: BLE001
            llm_structured = None
        if llm_structured:
            structured = llm_structured
    if not structured:
        raise HTTPException(422, "Could not extract resume structure from this file.")

    out_pdf = os.path.join(TMP_DIR, "%s_fixed.pdf" % sid)
    # A genuine 2+ page original is NEVER compressed onto one page:
    # allow its own page count and let template_engine ship multi-page
    # output at the comfortable (un-shrunk) preset.
    orig_pages = int((s["parsed"] or {}).get("n_pages") or 1)
    try:
        template_engine.generate_pdf(structured, template, out_path=out_pdf,
                                     max_pages=max(1, orig_pages))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, "PDF generation failed: %s" % e)

    # Re-score the generated PDF for the "after" side of the diff.
    fixed_parsed = resume_parser.parse_pdf(out_pdf)
    after_scores = scoring.score_resume(fixed_parsed)
    session_store.update(sid, fixed_pdf_path=out_pdf, after_scores=after_scores,
                         fixed_template=template, fixed_structured=structured)

    fixed_pages = int(fixed_parsed.get("n_pages") or 1)
    multi_reason = None
    if fixed_pages > 1:
        multi_reason = ("Original content requires multiple pages - the "
                        "fixed PDF keeps %d page(s) at full readable font "
                        "size instead of compressing to one." % fixed_pages)
    headers = {"Content-Disposition": 'attachment; filename="resume_fixed.pdf"',
               "X-Overall-Before": str(s["initial_scores"]["overall"]),
               "X-Overall-After": str(after_scores["overall"]),
               "X-Multi-Page": "true" if fixed_pages > 1 else "false",
               "X-Multi-Page-Reason": multi_reason or "",
               "Access-Control-Expose-Headers":
                   "Content-Disposition,X-Overall-Before,X-Overall-After,"
                   "X-Multi-Page,X-Multi-Page-Reason"}
    return FileResponse(out_pdf, media_type="application/pdf", headers=headers)


# ---------------------------------------------------------------- 7. rescore

@app.get("/rescore/{sid}")
def rescore(sid: str):
    s = _session_or_404(sid)
    after = s.get("after_scores")
    if after is None:
        raise HTTPException(404, "No fixed PDF yet. POST /generate/%s first." % sid)
    return {"before": s["initial_scores"], "after": after,
            "template": s.get("fixed_template", "classic")}


# ---------------------------------------------------------------- extras

@app.get("/original/{sid}")
def original(sid: str):
    """Serve the uploaded original PDF for before-side preview."""
    s = _session_or_404(sid)
    path = s.get("original_path", "")
    if not path or not os.path.exists(path) or not path.lower().endswith(".pdf"):
        raise HTTPException(404, "Original PDF preview unavailable for this file.")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": "inline"})


@app.get("/health")
def health():
    return {"status": "ok",
            "gemini": llm_service.gemini_available(),
            "pdf_engine": ("weasyprint" if template_engine._HAS_WEASYPRINT
                           else "xhtml2pdf")}
