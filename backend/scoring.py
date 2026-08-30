"""Rule-based scoring: ATS parseability score + visual/recruiter score.

Every check returns {check, passed, reason} so the UI can explain itself.
Pure Python, deterministic, no ML.
"""
from __future__ import annotations

import re

from parser import STANDARD_FONTS, CORE_SECTIONS, is_scanned


def _result(check, passed, reason):
    return {"check": check, "passed": bool(passed), "reason": reason}


def _finalize(checks, weights):
    earned = sum(weights[c["check"]] for c in checks if c["passed"])
    total = sum(weights.values())
    return {"score": round(earned / total * 100), "checks": checks}


# ---------------------------------------------------------------- ATS score

def ats_score(parsed: dict) -> dict:
    checks = []
    weights = {
        "machine_readable_text": 25,
        "single_column": 15,
        "no_photos": 10,
        "no_tables_or_textboxes": 15,
        "standard_sections": 15,
        "contact_in_body": 10,
        "standard_fonts": 5,
        "reasonable_length": 5,
    }

    scanned = is_scanned(parsed)
    checks.append(_result(
        "machine_readable_text", not scanned,
        "PDF appears to be an image scan - no selectable text for the ATS to read."
        if scanned else "Text is selectable and machine-readable."))

    multi = parsed.get("multicolumn", False)
    checks.append(_result(
        "single_column", not multi,
        "Multi-column layout detected - most ATS parsers scramble or drop side columns."
        if multi else "Single-column layout parses cleanly in ATS systems."))

    n_photos = parsed.get("photo_like_images", 0)
    checks.append(_result(
        "no_photos", n_photos == 0,
        ("%d embedded photo/image(s) detected - ATS parsers skip images "
         "entirely and recruiters increasingly expect no photo; prefer "
         "text links over graphics." % n_photos)
        if n_photos else "No photos or embedded images - ATS-safe."))

    tables = parsed.get("has_tables", False)
    checks.append(_result(
        "no_tables_or_textboxes", not tables,
        "Tables/text-boxes detected - ATS parsers often read table cells out of order."
        if tables else "No tables or text-boxes confusing the parser."))

    found = [k for k in CORE_SECTIONS if k in (parsed.get("sections") or {})]
    ok = len(found) >= 2
    missing = [s.title() for s in CORE_SECTIONS if s not in found]
    checks.append(_result(
        "standard_sections", ok,
        ("Standard section headers found: %s." % ", ".join(s.title() for s in found))
        if ok else
        "Missing standard headers (%s) - recruiters and ATS both scan for these."
        % ", ".join(missing)))

    hf = parsed.get("contact_in_header_footer", False)
    contact = parsed.get("contact") or {}
    has_contact = any(contact.get(k) for k in ("email", "phone"))
    ok = has_contact and not hf
    reason = "Contact info found in body text."
    if not has_contact:
        reason = "No email/phone detected near the top of the resume."
    elif hf:
        reason = ("Contact info sits in a page header/footer - many ATS tools "
                  "skip headers and footers entirely.")
    checks.append(_result("contact_in_body", ok, reason))

    fonts = [f.lower() for f in parsed.get("fonts", [])]
    fonts = [f for f in fonts if not _ICON_FONT_RE.search(f)]
    nonstd = [f for f in fonts
              if f and not any(f.startswith(s) or s in f for s in STANDARD_FONTS)
              and not _LATEX_FONT_RE.match(f)
              and not _SUBSET_FONT_RE.match(f)]
    ok = len(nonstd) == 0
    checks.append(_result(
        "standard_fonts", ok,
        ("Non-standard fonts detected (%s) which some ATS render incorrectly."
         % ", ".join(nonstd[:3])) if not ok else "Standard, ATS-safe fonts used."))

    pages = parsed.get("n_pages", 1)
    ok = 1 <= pages <= 3
    checks.append(_result(
        "reasonable_length", ok,
        "%d page(s) - within acceptable range." % pages
        if ok else "%d pages is unusual; aim for 1-2 pages." % pages))

    return _finalize(checks, weights)


# ---------------------------------------------------------------- visual score

_LATEX_FONT_RE = re.compile(r"^(cm|lm)[a-z]{0,4}\d*$")  # cmr10, cmbx12, lmr...
# Decorative icon/brand fonts carry only single glyphs (LinkedIn, GitHub
# marks) - they never render body text, so they are irrelevant to both the
# ATS font check and the visual family count.
_ICON_FONT_RE = re.compile(r"fontawesome|brands|-solid|glyphicons|"
                           r"brandicons", re.IGNORECASE)
# Word/LibreOffice embed standard families under subset names like
# "sfrm0900"; the text layer extracts normally, so subset names are not an
# ATS risk.
_SUBSET_FONT_RE = re.compile(r"^[a-z]{2,6}\d{2,5}$", re.IGNORECASE)


def _font_family(name: str) -> str:
    """Collapse embedded font style variants into their family.

    LaTeX PDFs embed every style separately (cmr10, cmbx12, cmsy10...) but
    visually use ONE family - counting raw names would flag clean LaTeX
    resumes as messy.
    """
    n = re.sub(r"\d+", "", (name or "").lower())
    for prefix, fam in (("cm", "computer-modern"), ("lm", "latin-modern"),
                        ("nimbus", "nimbus"), ("urw", "urw")):
        if n.startswith(prefix):
            return fam
    return n.split("-")[0].split(".")[0]


def visual_score(parsed: dict) -> dict:
    checks = []
    weights = {
        "font_count": 25,
        "size_consistency": 25,
        "whitespace_balance": 20,
        "bullet_consistency": 15,
        "page_length_appropriate": 15,
    }

    families = {_font_family(f) for f in parsed.get("fonts", [])
                if f and not _ICON_FONT_RE.search(f.lower())}
    n_fonts = len(families)
    ok = n_fonts <= 3
    checks.append(_result(
        "font_count", ok,
        "%d distinct font families used (>3 looks messy). Pick one font family."
        % n_fonts if not ok else
        "%d font family(ies) used - clean and consistent." % max(1, n_fonts)))

    sizes = parsed.get("sizes", [])
    lines = parsed.get("lines", [])
    body = [l for l in lines if not l.get("bold")]
    if sizes and body:
        counts = {}
        for l in body:
            counts[l["size"]] = counts.get(l["size"], 0) + 1
        dominant_size, dominant_n = max(counts.items(), key=lambda kv: kv[1])
        ratio = dominant_n / len(body)
        # Strays are measured among BODY (non-bold) text only - headers,
        # dates and the name are *supposed* to use different sizes.
        body_sizes = {l["size"] for l in body}
        stray = sorted(s for s in body_sizes
                       if abs(s - dominant_size) <= 1.2 and s != dominant_size)
        ok = ratio >= 0.55 and len(stray) <= 2
        checks.append(_result(
            "size_consistency", ok,
            ("Body text jumps between slightly-different sizes around %.1fpt - "
             "looks sloppy; normalize to one size." % dominant_size)
            if not ok else
            "Body text consistently uses ~%.1fpt." % dominant_size))
    else:
        checks.append(_result("size_consistency", True,
                              "Font size data unavailable; assumed consistent."))

    cpp = parsed.get("avg_chars_per_page", 0)
    ok = 500 <= cpp <= 5200
    if cpp < 500:
        reason = "Page looks nearly empty (%d chars/page) - poor use of whitespace." % cpp
    elif cpp > 5200:
        reason = "Walls of text (%d chars/page) - cramped and hard to skim." % cpp
    elif cpp < 900:
        reason = "On the sparse side (%d chars/page) but acceptably formatted." % cpp
    else:
        reason = "Healthy text density (~%d chars/page)." % cpp
    checks.append(_result("whitespace_balance", ok, reason))

    bullets = [l["text"] for l in lines if l.get("bullet")]
    if len(bullets) >= 4:
        lens = [len(b.split()) for b in bullets]
        mean = sum(lens) / len(lens)
        var = sum((x - mean) ** 2 for x in lens) / len(lens)
        cv = (var ** 0.5) / mean if mean else 0
        ok = cv < 0.75
        checks.append(_result(
            "bullet_consistency", ok,
            ("Bullet lengths vary wildly (some %d words, others %d) - tighten "
             "them to 1-2 lines each." % (max(lens), min(lens)))
            if not ok else "Bullet points are consistent in length."))
    else:
        checks.append(_result(
            "bullet_consistency", False,
            "Few or no bullet points - dense paragraphs get skipped by recruiters."))

    pages = parsed.get("n_pages", 1)
    ok = pages <= 2
    checks.append(_result(
        "page_length_appropriate", ok,
        "1-2 pages is right for most experience levels." if ok
        else "%d pages - trim it down; recruiters rarely read past page 2." % pages))

    return _finalize(checks, weights)


# ------------------------------------------------------- content quality score

# Bullets opening with these are strong; anything else is neutral.
STRONG_VERBS = {
    "architected", "engineered", "designed", "developed", "built",
    "implemented", "created", "led", "managed", "owned", "launched",
    "optimized", "automated", "integrated", "orchestrated", "modeled",
    "streamlined", "secured", "scaled", "reduced", "increased", "improved",
    "delivered", "shipped", "migrated", "deployed",
}
# Weak/vague openers - actively penalized (same families as the red-flag
# checker, but here they cost real score points).
WEAK_OPENERS = (
    "responsible for", "worked on", "worked with", "helped with",
    "helped to", "assisted with", "assisted in", "participated in",
    "involved in", "tasked with", "was part of", "duties included",
)
# Concrete technologies/frameworks/systems count as depth signals; generic
# industry phrases do not.
TECH_TERMS = {
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "rust",
    "react", "redux", "next.js", "node.js", "express", "django", "flask",
    "fastapi", "spring", "tailwind", "bootstrap", "html5", "css3",
    "docker", "kubernetes", "redis", "mongodb", "postgresql", "mysql",
    "neo4j", "pinecone", "langchain", "langgraph", "gemini", "openai",
    "pytorch", "tensorflow", "keras", "huggingface", "aws", "gcp", "azure",
    "graphql", "rest", "websockets", "jwt", "oauth", "kafka", "spark",
    "git", "linux", "vs code extension", "mern", "jest", "cypress",
    "selenium", "pandas", "numpy", "scikit-learn", "figma", "flutter",
    "swift", "kotlin", "android",
}
GENERIC_PHRASES = (
    "web development", "software development", "teamwork", "communication",
    "hard working", "hard-working", "leadership skills", "team player",
    "quick learner", "good knowledge", "various tasks",
)
QUANT_RE = re.compile(
    r"\d+\s*%|\b\d{1,3}(?:,\d{3})+\b|\$\s*\d|\u20b9\s*\d|\b\d+\s*\+"
    r"|\+\s*\d+\b|\b\d+(?:\.\d+)?\s*[xX]\b|\b\d+k\b|\b\d{2,}\b")

CONTENT_DIM_WEIGHTS = {
    # ratio of bullets containing a number/metric/scale indicator
    "quantified_impact": 30,
    # distinct concrete technologies named across the resume
    "technical_depth": 20,
    # strong openers vs weak openers
    "action_verb_strength": 20,
    # share of substantive (>= MIN_SUBSTANTIVE_WORDS words) bullets
    "bullet_substance": 15,
    # number of project/experience entries and bullets-per-entry density
    "depth_breadth": 15,
}
MIN_SUBSTANTIVE_WORDS = 8   # under this a bullet is too vague to show work
MIN_DEPTH_ENTRIES = 2       # fewer projects/roles than this is thin
MIN_BULLETS_PER_ENTRY = 3   # 1-2 bullets per entry reads as shallow


def _content_bullets(structured: dict) -> list:
    """All bullets from entries-type sections (projects, experience, ...)."""
    out = []
    for sec in structured.get("sections", []):
        if sec.get("type") != "entries":
            continue
        for e in sec.get("entries", []):
            out += [b for b in e.get("bullets", []) if b]
    return out


def _entry_stats(structured: dict) -> tuple:
    """(#entries in project/experience-like sections, avg bullets per entry)."""
    n_entries, n_bullets = 0, 0
    for sec in structured.get("sections", []):
        if sec.get("type") != "entries":
            continue
        t = (sec.get("title") or "").lower()
        if any(k in t for k in ("education", "skill")):
            continue
        for e in sec.get("entries", []):
            n_entries += 1
            n_bullets += len(e.get("bullets", []) or [])
    avg = (n_bullets / n_entries) if n_entries else 0.0
    return n_entries, avg


def content_quality_score(parsed: dict) -> dict:
    """Content strength: would the described work survive recruiter scrutiny?

    Completely separate from ATS parseability and visual score - a structurally
    perfect resume can still score low here if the content is thin.
    """
    structured = parsed.get("structured") or {}
    bullets = _content_bullets(structured)
    total = len(bullets)
    dims = []

    def add(name, earned, reason):
        dims.append({"dimension": name, "earned": int(round(earned)),
                     "max": CONTENT_DIM_WEIGHTS[name], "reason": reason})

    if total == 0:
        return {"score": 0, "dimensions": [{
            "dimension": d, "earned": 0, "max": w,
            "reason": "No bullet-point content found."}
            for d, w in CONTENT_DIM_WEIGHTS.items()]}

    lowered = [re.sub(r"\s+", " ", b).strip().lower() for b in bullets]

    # 1. quantified impact ---------------------------------------------------
    quant = sum(1 for b in lowered if QUANT_RE.search(b))
    ratio = quant / total
    add("quantified_impact", CONTENT_DIM_WEIGHTS["quantified_impact"] * ratio,
        "%d of %d bullets contain a number/metric (%d%%)."
        % (quant, total, round(ratio * 100)))

    # 2. technical depth -----------------------------------------------------
    blob = " ".join(lowered)
    found = sorted({t for t in TECH_TERMS if re.search(
        r"(?<![\w.-])" + re.escape(t) + r"(?![\w-])", blob)})
    generic_hit = [g for g in GENERIC_PHRASES if g in blob]
    tech_pts = min(float(CONTENT_DIM_WEIGHTS["technical_depth"]),
                   4.0 * len(found))
    if generic_hit and not found:
        tech_pts = 0.0
    add("technical_depth", tech_pts,
        ("%d specific technologies named (%s)." %
         (len(found), ", ".join(found[:6])))
        if found else
        (("Only generic phrasing (%s) - no concrete technologies."
          % ", ".join(generic_hit[:3])) if generic_hit
         else "No recognizable technologies named."))

    # 3. action verb strength --------------------------------------------------
    strong = 0
    for b in lowered:
        first = b.split(": ", 1)[-1].split()[0].strip("0123456789.)-")
        strong += 1 if first in STRONG_VERBS else 0
    weak = sum(1 for b in lowered if b.startswith(WEAK_OPENERS))
    verb_pts = max(0.0, CONTENT_DIM_WEIGHTS["action_verb_strength"]
                   * (strong / total) * (1 - weak / total) - 2 * weak)
    add("action_verb_strength", verb_pts,
        "%d/%d bullets open with a strong action verb%s."
        % (strong, total,
           ("; %d use weak openers ('responsible for', 'worked on'...)" % weak)
           if weak else "."))

    # 4. bullet substance --------------------------------------------------------
    substantive = sum(1 for b in bullets
                      if len(b.split()) >= MIN_SUBSTANTIVE_WORDS)
    add("bullet_substance",
        CONTENT_DIM_WEIGHTS["bullet_substance"] * (substantive / total),
        "%d/%d bullets are at least %d words long."
        % (substantive, total, MIN_SUBSTANTIVE_WORDS))

    # 5. project/experience count & density ---------------------------------------
    n_entries, avg_bullets = _entry_stats(structured)
    entry_pts = min(10.0, 3.33 * n_entries)
    density_pts = min(5.0, (avg_bullets / MIN_BULLETS_PER_ENTRY) * 5.0)
    add("depth_breadth", entry_pts + density_pts,
        "%d project/experience entries, averaging %.1f bullets each."
        % (n_entries, avg_bullets))

    earned = sum(d["earned"] for d in dims)
    max_total = sum(CONTENT_DIM_WEIGHTS.values())
    checks = [{
        "check": d["dimension"],
        "passed": d["earned"] >= 0.6 * d["max"],
        "reason": "%s (%d/%d pts)" % (d["reason"], d["earned"], d["max"]),
    } for d in dims]
    return {"score": round(earned / max_total * 100),
            "dimensions": dims, "checks": checks}


# ---------------------------------------------------------------- combined

def score_resume(parsed: dict) -> dict:
    ats = ats_score(parsed)
    vis = visual_score(parsed)
    content = content_quality_score(parsed)
    overall = round(ats["score"] * 0.6 + vis["score"] * 0.4)
    # `content` is deliberately NOT blended into `overall` - structure can only
    # take a resume so far; content quality is reported as its own category.
    return {"ats": ats, "visual": vis, "content": content, "overall": overall}
