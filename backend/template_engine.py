"""Template engine: structured resume JSON -> HTML (Jinja2) -> PDF.

Primary renderer is WeasyPrint; if its native GTK dependencies are missing
(common on Windows), falls back to pure-Python xhtml2pdf so the demo always
produces a PDF.
"""
from __future__ import annotations

import copy
import html as _html
import io
import os
import re
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
AVAILABLE_TEMPLATES = ["classic", "modern", "cv_academic", "latex_clean"]

# --- configurable rendering rules -------------------------------------------
# A CGPA/GPA at or above this value (out of 10) earns Education a top slot
# (right after contact info, before Summary). Below it - or missing entirely -
# Education stays in its normal position AFTER Projects.
EDUCATION_TOP_CGPA = 8.5
# Percentage threshold used only when no CGPA/GPA appears anywhere in the
# Education section ("82%" class-XII marks etc.).
EDUCATION_TOP_PERCENT = 85.0

_CGPA_RE = re.compile(
    r"\b(?:cgpa|gpa)\s*[:\-]?\s*([0-9]{1,2}(?:\.[0-9]+)?)", re.IGNORECASE)
_PCT_RE = re.compile(r"\b([0-9]{1,2}(?:\.[0-9]+)?)\s*%", re.IGNORECASE)
# "Languages: C++, Python ..." -> bold label + items.  Label must be short
# (<40 chars) so a sentence that happens to contain a colon is not split.
_SKILL_LABEL_RE = re.compile(r"^([A-Z][A-Za-z0-9 ,&/+.'()-]{1,38}?):\s*(.+)$")

# Education score DISPLAY form: a parsed 'CGPA: 9.07/10' renders as
# 'CGPA: 9.07' - bare CGPA, no '/10' suffix (user spec).  Percentages
# ('93%', '93.80%') and non-10 scales ('3.7/4.0') pass through untouched.
_SCORE_SCALE_RE = re.compile(r"/\s*10(?:\.0)?\s*$")

# Education date compaction (Kanish wrap fix): full month names in the
# row-1 right cell ('Punjab, India · September 2022-Present') push the date
# onto a second line.  Abbreviating the month keeps every education row on
# one line without dropping the location.
_MONTH_ABBR = {
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr",
    "june": "Jun", "july": "Jul", "august": "Aug", "september": "Sep",
    "october": "Oct", "november": "Nov", "december": "Dec",
    # already-abbreviated / short forms pass through unchanged
    "jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr", "may": "May",
    "jun": "Jun", "jul": "Jul", "aug": "Aug", "sep": "Sep", "sept": "Sep",
    "oct": "Oct", "nov": "Nov", "dec": "Dec",
}
_MONTH_WORD_RE = re.compile(r"\b([A-Za-z]+)(?=\s|\.)")


def _compact_date(date: str) -> str:
    """'September 2022-Present' -> 'Sep 2022-Present'.  Month words only;
    years, 'Present', 'Expected' etc. are left alone."""
    def repl(m):
        return _MONTH_ABBR.get(m.group(1).lower(), m.group(1))
    return _MONTH_WORD_RE.sub(repl, date or "").strip()


def _display_score(score: str) -> str:
    return _SCORE_SCALE_RE.sub("", score or "").strip()


def _section_text(sec: dict) -> str:
    """Flatten every piece of text in a structured section into one string."""
    parts = [sec.get("title", ""), sec.get("text", "")]
    for it in sec.get("items", []) or []:
        parts.append(it if isinstance(it, str) else str(it))
    for e in sec.get("entries", []) or []:
        parts += [e.get("title", ""), e.get("meta", ""), e.get("date", "")]
        parts += e.get("bullets", []) or []
    return " ".join(str(p) for p in parts)


def _is_education(sec: dict) -> bool:
    k = (sec.get("key") or "").lower()
    if k == "education":
        return True
    t = (sec.get("title") or "").lower()
    return "educat" in t or "academ" in t


def _academic_metrics(sections: list) -> tuple:
    """(best CGPA, best percent) found in Education sections.

    The degree CGPA is the flagship metric, so when ANY CGPA/GPA exists the
    percentage marks are ignored for placement purposes.
    """
    best_cgpa = None
    best_pct = None
    for sec in sections:
        if not _is_education(sec):
            continue
        blob = _section_text(sec)
        m = _CGPA_RE.search(blob)
        if m:
            v = float(m.group(1))
            if 0 < v <= 10:
                best_cgpa = v if best_cgpa is None else max(best_cgpa, v)
        for pm in _PCT_RE.finditer(blob):
            v = float(pm.group(1))
            if 0 < v <= 100:
                best_pct = v if best_pct is None else max(best_pct, v)
    return best_cgpa, best_pct


def _is_anchor_section(sec: dict) -> bool:
    return ((sec.get("key") or "").lower() in ("projects", "experience")
            or (sec.get("title") or "").strip().lower() in (
                "projects", "experience", "work experience"))


def _classify_bucket(sec: dict) -> str:
    # Canonical parser key wins (a section titled 'Portfolio' or 'Skills
    # Summary' must bucket by WHAT it is, not how its source labeled it).
    k = (sec.get("key") or "").lower()
    if k.endswith(("education", "summary", "skills", "experience",
                   "projects", "awards", "certifications")):
        return k.rsplit(":", 1)[-1] if k.startswith("custom") else k
    if k == "achievements":
        return "awards"
    if k == "roles":
        return "custom"
    t = (sec.get("title") or "").lower()
    if "educat" in t:
        return "education"
    if any(w in t for w in ("summary", "profile", "about", "objective")):
        return "summary"
    if "skill" in t or "technolog" in t or "stack" in t:
        return "skills"
    if "experience" in t or "employment" in t or "work history" in t:
        return "experience"
    if "project" in t:
        return "projects"
    if any(w in t for w in ("award", "achievement", "honor", "honour",
                            "accomplishment", "recognition")):
        return "awards"
    if "certif" in t:
        return "certifications"
    return "custom"


def _order_sections(sections: list) -> list:
    """EXACT canonical render order, built as one explicit list.

    1. Name + contact links (header, outside this list)
    2. Education            - ONLY when CGPA >= EDUCATION_TOP_CGPA
                              (or pct >= EDUCATION_TOP_PERCENT with no CGPA)
    3. Summary
    4. Skills               - when present
    5. Experience           - when present
    6. Projects
    7. Awards/Achievements  - when present
    8. Certifications + custom sections (kept, original labels)
    9. Education            - when metric is below threshold / missing

    Nothing is dropped: every parsed section lands in exactly one bucket.
    """
    buckets = {"education": [], "summary": [], "skills": [], "experience": [],
               "projects": [], "awards": [], "certifications": [],
               "custom": []}
    for s in sections:
        buckets.setdefault(_classify_bucket(s), []).append(s)

    cgpa, pct = _academic_metrics(sections)
    if cgpa is not None:
        strong = cgpa >= EDUCATION_TOP_CGPA
        basis = "cgpa=%s" % cgpa
    else:
        strong = pct is not None and pct >= EDUCATION_TOP_PERCENT
        basis = "pct=%s (no CGPA found)" % pct

    edu = buckets["education"]
    ordered = []
    if strong and edu:
        ordered += edu                       # position 2: right after contacts
    ordered += buckets["summary"]            # Summary
    ordered += buckets["experience"]         # Experience
    ordered += buckets["projects"]           # Projects
    ordered += buckets["skills"]             # Skills AFTER Projects
    ordered += buckets["awards"]             # Achievements/Awards
    ordered += buckets["certifications"]     # kept, own label
    ordered += buckets["custom"]             # unknown sections, never dropped
    if not strong and edu:
        ordered += edu                       # last: after Achievements

    decision = "TOP - right after contacts" if strong else \
        "END - after Achievements"
    print("[education-placement] parsed %s; thresholds cgpa>=%.1f pct>=%.1f"
          " -> Education %s | order=%s"
          % (basis, EDUCATION_TOP_CGPA, EDUCATION_TOP_PERCENT, decision,
             [s.get("title") for s in ordered]), file=sys.stderr)
    return ordered


# C.7: known multi-word phrases must never split across render lines inside
# skills lists ("... Object" / "Oriented Programming").  Matching phrases get
# NBSP-joined so the wrap point moves to a phrase boundary.
_PHRASE_PROTECT = [
    "Object Oriented Programming", "Data Structures and Algorithms",
    "Operating Systems", "Database Management Systems",
    "Machine Learning", "Artificial Intelligence", "Data Science",
    "Deep Learning", "Computer Science", "Software Development",
    "Web Development", "Version Control", "Problem Solving",
    "Natural Language Processing", "Full Stack Development",
]


# Leading source-project numbering ("1) AlgoZen...", "3) GraphRAG...",
# "(2) Foo", "4. Bar").  NEVER rendered - every generated resume shows
# clean unnumbered titles even when the source resume numbered them.
_TITLE_NUMBER_RE = re.compile(r"^\s*(?:\(\d{1,2}\)|\d{1,2}\s*[\)\]\.])\s*")


def _strip_title_number(text: str) -> str:
    return _TITLE_NUMBER_RE.sub("", text or "").strip().rstrip()


def _protect_phrases(text: str) -> str:
    t = str(text)
    for ph in _PHRASE_PROTECT:
        pat = re.compile(re.escape(ph).replace("\\ ", "[ ]"), re.IGNORECASE)
        t = pat.sub(lambda m: m.group(0).replace(" ", "\u00a0"), t)
    return t


def _prep_skills(sections: list) -> list:
    """Split each skills line into {label, items} so templates can bold the
    category label ("Languages:", "Tools & Platforms:") exactly like the
    original resumes do."""
    for sec in sections:
        if sec.get("type") != "skills":
            continue
        rows = []
        for item in sec.get("items", []) or []:
            m = _SKILL_LABEL_RE.match(str(item).strip())
            if m:
                # NB: key must not be "items" - Jinja resolves row.items to
                # dict.items() (the method) before the dict key.
                rows.append({"label": m.group(1),
                             "rest": _protect_phrases(m.group(2))})
            else:
                rows.append({"label": "",
                             "rest": _protect_phrases(str(item))})
        sec["skill_rows"] = rows
    return sections


# --- selective bolding + link labels ----------------------------------------

_EMAIL_FULL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_PHONE_FULL_RE = re.compile(r"^\+?[\d][\d\s().-]{7,}\d$")
_METRIC_RE = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s*(%|\+|x\b|\u00d7)")
# Link-shaped token inside a contact string ("https://..." or "github.com/x").
URL_SEARCH_RE = re.compile(
    r"(?:https?://|www\.)[^\s|,\u00b7\u2022]+"
    r"|(?:github\.com|gitlab\.com|linkedin\.com|leetcode\.com"
    r"|medium\.com)/[^\s|,\u00b7\u2022]+",
    re.IGNORECASE)

_DOMAIN_LABELS = [
    ("linkedin.com", "LinkedIn"), ("github.com", "GitHub"),
    ("gitlab.com", "GitLab"), ("leetcode.com", "LeetCode"),
    ("hackerrank.com", "HackerRank"), ("kaggle.com", "Kaggle"),
    ("medium.com", "Blog"), ("dev.to", "Blog"),
    ("marketplace.visualstudio.com", "VS Extension"),
    ("netlify.app", "Portfolio"), ("vercel.app", "Portfolio"),
    ("github.io", "Portfolio"), ("onrender.com", "Demo"),
    ("herokuapp.com", "Demo"), ("behance.net", "Behance"),
]

# Contact-header icon chips (engine-safe: styled letter/symbol chips instead
# of brand fonts).  kind -> glyph shown inside the colored chip.
ICON_GLYPHS = {"email": "@", "phone": "#", "linkedin": "in",
               "github": "GH", "gitlab": "GL", "leetcode": "LC",
               "hackerrank": "HR", "kaggle": "K", "blog": "B",
               "vsext": "VS", "portfolio": "P", "demo": "D",
               "behance": "Be", "web": "W"}
ICON_COLORS = {"email": "#c5221f", "phone": "#188038", "linkedin": "#0a66c2",
               "github": "#24292e", "gitlab": "#fc6d26", "leetcode": "#ffa116",
               "hackerrank": "#2ec866", "kaggle": "#20beff", "blog": "#ff6b00",
               "vsext": "#0078d4", "portfolio": "#5f6368", "demo": "#34a853",
               "behance": "#1769ff", "web": "#70757a"}

# domain substring -> contact-item kind (personal header classification)
_DOMAIN_KINDS = [
    ("linkedin.com", "linkedin"), ("github.com", "github"),
    ("gitlab.com", "gitlab"), ("leetcode.com", "leetcode"),
    ("hackerrank.com", "hackerrank"), ("kaggle.com", "kaggle"),
    ("medium.com", "blog"), ("dev.to", "blog"),
    ("marketplace.visualstudio.com", "vsext"),
    ("netlify.app", "portfolio"), ("vercel.app", "portfolio"),
    ("github.io", "portfolio"), ("onrender.com", "demo"),
    ("herokuapp.com", "demo"), ("behance.net", "behance"),
]


def _clean_href(url: str) -> str:
    """Strip tracking junk (utm_*), then guarantee an ABSOLUTE https URL.
    Parsed contacts often arrive scheme-less ('linkedin.com/in/x' or
    'www.github.com/y') - without the scheme PDF viewers treat the link
    annotation as relative and clicking does nothing (Muskan bug)."""
    u = url.strip()
    if "utm_" in u:
        base, _, query = u.partition("?")
        kept = [p for p in query.split("&")
                if p and not p.lower().startswith("utm_")]
        u = base + ("?" + "&".join(kept) if kept else "")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", u):
        u = "https://" + re.sub(r"^(?:www\d?\.)?", "", u, flags=re.I)
    return u


def _link_label(url: str) -> str:
    low = url.lower()
    for domain, label in _DOMAIN_LABELS:
        if domain in low:
            return label
    host = re.sub(r"^(?:https?://|www\.)", "", low).split("/")[0]
    base = host.split(".")[0] if "." in host else host
    return base.capitalize() or "Link"


def _contact_label(url: str) -> str:
    """Label for the PERSONAL contact header.  Recognized domains get their
    brand label; ANY other personal site is 'Website' - never the raw URL
    slug (Sarthak bug: 'sarthakrawat.me' rendered as 'Sarthakrawat')."""
    low = url.lower()
    for domain, label in _DOMAIN_LABELS:
        if domain in low:
            return label
    return "Website"


def _contact_items(contacts: list) -> list:
    """Classify each parsed contact into {kind, label, href} so templates can
    render an icon chip plus a short clickable label - raw URLs never appear
    as visible text.  Only PERSONAL contacts reach this point; project links
    live on their entry objects."""
    items = []

    def add(kind, display, href=""):
        items.append({"kind": kind,
                      "glyph": ICON_GLYPHS.get(kind, "W"),
                      "color": ICON_COLORS.get(kind, "#70757a"),
                      "label": _html.escape(display),
                      "href": _html.escape(href, quote=True)})

    def _norm_url(u):
        u = re.sub(r"^(?:https?://)?(?:www\.)?", "", u.strip().lower(), flags=re.I)
        return u.rstrip("/")

    seen = set()
    for c in contacts or []:
        c = str(c).strip()
        if not c:
            continue
        low = c.lower()
        if _EMAIL_FULL_RE.match(c):
            key = ("email", low)
        elif _PHONE_FULL_RE.match(c) and sum(ch.isdigit() for ch in c) >= 8:
            key = ("phone", re.sub(r"\D", "", c)[-10:])
        else:
            m = URL_SEARCH_RE.search(c)
            if m:
                href = _clean_href(m.group(0))
                kind = next((k for dom, k in _DOMAIN_KINDS if dom in low), "web")
                key = (kind, _norm_url(href))
            else:
                key = ("text", low)
        if key in seen:
            continue  # same contact repeated in a second form (Sarthak bug:
            # 'linkedin.com/in/x' AND 'https://linkedin.com/in/x/')
        seen.add(key)
        if _EMAIL_FULL_RE.match(c):
            add("email", c, "mailto:" + c)
            continue
        if _PHONE_FULL_RE.match(c) and sum(ch.isdigit() for ch in c) >= 8:
            add("phone", c)
            continue
        m = URL_SEARCH_RE.search(c)
        if m:
            href = _clean_href(m.group(0))
            kind = next((k for dom, k in _DOMAIN_KINDS if dom in low), "web")
            add(kind, _contact_label(href), href)
    return items


def _linkify_urls(escaped: str) -> str:
    """Turn URL-shaped tokens in ALREADY-ESCAPED text into real anchors
    with friendly labels (LinkedIn/GitHub/...).  Runs on bullet/summary
    text after metric bolding, when the only tags present are attribute-less
    <strong> pairs - so it can never match inside an attribute.  Makes every
    link in the document clickable, not just the contact-header ones."""
    def _sub(m):
        try:
            href = _html.escape(_clean_href(m.group(0)), quote=True)
        except Exception:  # noqa: BLE001 - never break rendering on a bad URL
            return m.group(0)
        label = _html.escape(_link_label(m.group(0)))
        return '<a href="%s">%s</a>' % (href, label)
    return URL_SEARCH_RE.sub(_sub, escaped)


def _bold_metrics(text: str) -> Markup:
    """Escape bullet text, then bold standout metrics (40%, 7+, 300+, 12x)
    so numbers draw the eye without bolding whole sentences.  URL-shaped
    tokens become clickable anchors (friendly label, absolute href)."""
    esc = _html.escape(text)
    out = _METRIC_RE.sub(r"<strong>\1\2</strong>", esc)
    return Markup(_linkify_urls(out))


def _sanitize_bold_phrase(ph: str) -> str:
    """Trim an LLM-chosen bold phrase so it never drags in stray glyphs:
    drop dangling punctuation/parens and cap the length (~60 chars), so
    the bold reads like a clean key term (Vikas bar) not a whole clause."""
    p = re.sub(r"\s+", " ", str(ph or "")).strip()
    p = p.strip(" \t.,;:!?()[]{}\u2018\u2019\u201c\u201d\u2013\u2014")
    bal = p.count("(") - p.count(")")
    if bal < 0 and p.endswith((")", "]")):
        last = max(p.rfind("("), p.rfind("["))
        if last > 0:
            p = p[:last].strip()
    if len(p) > 60:
        p = p[:60].rstrip(" ,;:").strip()
    return p


def _bold_summary(text: str) -> Markup:
    """C.8 dual-path Summary bolding.

    Path A (Gemini key configured): the LLM picks 3-5 key noun phrases and
    we bold them (escaped, verbatim-verified, capped at 5).
    Path B (no key / any API failure): deterministic metric-only bolding.
    """
    txt = str(text or "")
    phrases = None
    try:
        import llm_service as _llm
        if _llm.gemini_available():
            phrases = _llm.summary_key_phrases(txt)
            if phrases:
                print("[summary-bold] gemini path: %d phrase(s)"
                      % len(phrases), file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - never let LLM break rendering
        print("[summary-bold] LLM path failed (%s) - rules fallback" % e,
              file=sys.stderr)
        phrases = None
    if not phrases:
        return _bold_metrics(txt)
    esc = _html.escape(txt)
    out, bolded = esc, 0
    for ph in phrases:
        ph = _sanitize_bold_phrase(ph)
        if len(ph) < 3:
            continue
        pat = re.compile(re.escape(_html.escape(ph)).replace(r"\ ", "[ ]"),
                         re.IGNORECASE)
        out, n = pat.subn(lambda m: "<strong>%s</strong>" % m.group(0),
                          out, count=1)
        bolded += n
    if not bolded:
        return _bold_metrics(txt)
    # Gemini path output has only attribute-less <strong> pairs, so it is
    # safe to linkify URL tokens here too (same invariant as _bold_metrics).
    return Markup(_linkify_urls(out))


_STATUS_TAG_RE = re.compile(
    r"^\(\s*(?:working\s*on\s*it|in\s*progress|ongoing|wip)\s*\)$", re.IGNORECASE)


# '(Extension ID: User.name)' suffix inside a project title (Harsh finding):
# rendered as a compact italic subtitle under the title line instead of
# wrapping the title mid-parenthesis onto an orphaned line.
_EXT_BADGE_RE = re.compile(
    r"\s*\(\s*Extension\s*ID\s*:\s*([^)]+?)\s*\)\s*", re.IGNORECASE)


def _prep_entries(sections: list) -> list:
    """Per-entry render prep: metric-bolded bullet HTML + project link fields."""
    for sec in sections:
        for e in sec.get("entries", []) or []:
            e["title"] = _strip_title_number(e.get("title", ""))
            title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
            m = _EXT_BADGE_RE.search(title)
            if m:
                e["ext_badge"] = "Extension ID: " + m.group(1).strip()
                title = re.sub(r"\s+", " ",
                               title[:m.start()] + " " + title[m.end():]).strip()
            # cosmetic: no trailing colon on entry titles ("... DeepStream:")
            title = re.sub(r"\s+[-\u2013|]\s*$", "", title).rstrip(":").rstrip()
            e["title"] = title
            # titles longer than ~58 chars shrink one step so they stay on a
            # single line (Kanish: 'Autonomous Object Detection System with
            # JetBot and DeepStream' wrapped in the 76% title column)
            e["title_long"] = len(title) > 58
            e["title_html"] = _entity_title_html(title)
            # '(Working on it)' style status tags belong in the RIGHT cell
            # (aligned like Link/Demo/GitHub), never inline after the title.
            if _STATUS_TAG_RE.match((e.get("meta") or "").strip()):
                e["status_tag"] = e["meta"].strip()
                e["meta"] = ""
            e["bullets_html"] = [_bold_metrics(b) for b in e.get("bullets", [])]
            uri = e.pop("link", None) if isinstance(e.get("link"), str) else None
            if uri:
                href = _clean_href(uri)
                e["link_href"] = _html.escape(href, quote=True)
                e["link_label"] = _html.escape(_link_label(href))
        if sec.get("type") == "paragraph":
            sec["text_html"] = _bold_summary(sec.get("text", ""))
    return sections


# --- two-mode template architecture ------------------------------------------
# MODE A "cv_academic"  - serif LaTeX/academic-CV identity (Kanish Chadha and
#                         Sarthak Rawat originals are the visual bar): tight
#                         density, institution-first education rows, bold used
#                         ONLY for entity names (company/school/project) and
#                         standout metrics.
# MODE B "latex_clean"  - the cleaner, more spacious project-focused identity
#                         (Vikas Gupta's LaTeX original is the bar), rendered
#                         in Computer Modern to match his source .tex output.
# Selection is automatic: a genuine Experience/Work section with real job
# entries -> Mode A; projects/education/skills only -> Mode B.

_EXPERIENCE_TITLE_RE = re.compile(
    r"experience|employment|work history|internship", re.IGNORECASE)


def _has_real_experience(sections: list) -> bool:
    for sec in sections:
        if not ((sec.get("key") or "").lower() == "experience"
                or _EXPERIENCE_TITLE_RE.search(sec.get("title") or "")):
            continue
        for e in sec.get("entries") or []:
            if (e.get("title") or "").strip():
                return True
    return False


def auto_template(resume: dict) -> str:
    """Mode A when real dated job entries exist, otherwise Mode B."""
    if _has_real_experience(resume.get("sections") or []):
        return "cv_academic"
    return "latex_clean"


_ENTITY_SPLIT_RE = re.compile(r"^(.{1,45}?)(\s*[|\u2013\u2014]\s*)(.+)$",
                              re.DOTALL)


def _entity_title_html(title: str) -> Markup:
    """Mode A title emphasis: bold ONLY the entity name (company / project
    name), never the full title line.  'Lumina | TypeScript, ...' renders
    'Lumina' bold with the tech stack in regular weight; a short standalone
    entity name ('Freight Tiger', 'Woostaa Housing Solutions Pvt. Ltd.') is
    bold in full; anything longer without a separator stays regular."""
    esc = _html.escape(title or "")
    # Wrap-orphan guard: glue the last two list tokens together ('...,
    # ChromaDB, GCP') so a wrap never strands a single item on its own
    # line (Sarthak: 'GCP' alone under the Lumina title).
    idx = esc.rfind(", ")
    if idx != -1:
        esc = esc[:idx] + ",&nbsp;" + esc[idx + 2:]
    m = _ENTITY_SPLIT_RE.match(esc)
    if m:
        return Markup("<strong>%s</strong><span class=\"trest\">%s%s</span>"
                      % (m.group(1), m.group(2), m.group(3)))
    if len(title or "") <= 70:
        return Markup("<strong>%s</strong>" % esc)
    return Markup(esc)


# 'Bengaluru, Karnataka' / 'Punjab, India' / 'Haridwar, Uttarakhand'
_LOC_LINE_RE = re.compile(r"[A-Z][A-Za-z .'-]+,\s*[A-Z][A-Za-z .'-]+")


def _merge_location_entries(sections: list) -> list:
    """Experience-section repair: a bare location line ('Bengaluru,
    Karnataka') that follows an entry with no bullets is the entry's
    workplace, not a new job - merge it in and never let it steal the
    next entry's bullets (Sarthak bug)."""
    for sec in sections:
        if not ((sec.get("key") or "").lower() == "experience"
                or any(w in (sec.get("title") or "").lower()
                       for w in ("experience", "employment", "work"))):
            continue
        ents = sec.get("entries") or []
        out = []
        for e in ents:
            prev = out[-1] if out else None
            ti = (e.get("title") or "").strip()
            if (prev is not None and ti
                    and _LOC_LINE_RE.fullmatch(ti) and len(ti) <= 32
                    and not (e.get("meta") or "").strip()
                    and not (e.get("date") or "").strip()
                    and not (prev.get("bullets") or [])):
                prev["bullets"] = e.get("bullets") or []
                prev["location"] = ti
                continue
            out.append(e)
        sec["entries"] = out
    return sections

# degree vs institution keywords (education field-order repair)
_DEG_RE = re.compile(
    r"bachelor|master|b\.?\s?tech|m\.?\s?tech|b\.\s?e\b|b\.?sc\b|m\.?sc\b"
    r"|diploma|secondary|class\s*(?:x{1,3}\b|ix\b|viii\b)|high school"
    r"|ph\.?d|associate'?s?", re.IGNORECASE)
_SCHOOL_RE = re.compile(
    r"university|institute|college|school|academy|iit\b|nit\b|iiit\b"
    r"|bits\b|polytechnic|bms\b", re.IGNORECASE)


def _shape_education(sections: list) -> list:
    """Education field-order repair.  Parsers glue degree+CGPA into the
    title and bury the institution in meta (Kanish: college 'missing').
    Normalizes each entry into {school, degree, location, score} so Mode A
    can render institution FIRST (bold, own line), degree below (regular),
    location + date right-aligned on the institution line."""
    for sec in sections:
        k = (sec.get("key") or "").lower()
        if k != "education" and not (
                "educat" in (sec.get("title") or "").lower()
                or "academ" in (sec.get("title") or "").lower()):
            continue
        # Score-only entries: right-rail rows like 'CGPA: 8.9/10' can parse
        # as their OWN education entry (read top-to-bottom they trail the
        # degree row).  They belong to the entry ABOVE - merge into its meta
        # so the shaper consumes the score into the right-aligned rail cell
        # under the date (Nirgun: CGPA rendered as a stray left row).
        merged = []
        for e in sec.get("entries") or []:
            prev = merged[-1] if merged else None
            ti = re.sub(r"[\u200b\u200c\u200d\ufeff]", "",
                        (e.get("title") or "")).strip()
            if (prev is not None and ti
                    and not (e.get("meta") or "").strip()
                    and not (e.get("date") or "").strip()
                    and not (e.get("bullets") or [])
                    and (_CGPA_RE.search(ti) or _PCT_RE.search(ti))
                    and ((prev.get("title") or "").strip()
                         or (prev.get("edu") or {}).get("degree"))):
                # never duplicate the score on a re-shape pass
                if not ((prev.get("edu") or {}).get("score") or "").strip():
                    prev["meta"] = ((prev.get("meta") or "").rstrip(" \u00b7")
                                    + " \u00b7 " + ti).strip()
                continue
            e["title"] = ti
            merged.append(e)
        sec["entries"] = merged
        for e in sec.get("entries") or []:
            school = degree = location = score = ""
            # idempotency: render_html runs the shaper on every attempt of
            # the one-page tightening loop.  A previous pass may already
            # have consumed meta/bullets into e["edu"]; without this guard
            # the second pass finds no score candidate and drops it
            # (Vinod: '93%'/'93.80%' vanished from the rendered rail).
            # invisible zero-width chars (PDF extraction artifacts) break
            # the score/scale regexes ('8.9/\u200b10') - strip them first
            e["meta"] = re.sub(r"[\u200b\u200c\u200d\ufeff]", "",
                               e.get("meta") or "")
            # dangling month fragment: a column-merged date can split at the
            # wrong point, stranding 'MM/' on the degree title while the date
            # lost its month ('B.Tech 08/' + '2023 - Present').  Re-attach so
            # the rail shows the full '08/2023 - Present'.
            _ti = (e.get("title") or "").strip()
            _dt = (e.get("date") or "").strip()
            _mf = re.search(r"(\d{1,2}/)\s*$", _ti)
            if _mf and re.match(r"^(19|20)\d{2}\b", _dt) \
                    and not _dt.startswith(_mf.group(1)):
                e["title"] = _ti[:_mf.start()].rstrip()
                e["date"] = _mf.group(1) + _dt
            prev_edu = e.get("edu") or {}
            meta_raw = e.get("meta") or ""
            meta_parts = [p for p in re.split(r";|\s+\u00b7\s+", meta_raw)
                          if p.strip()]
            cand = []
            if (e.get("title") or "").strip():
                cand.append(("title", e["title"]))
            cand += [("meta", p) for p in meta_parts]
            cand += [("bullet", b) for b in e.get("bullets") or []]
            for src, raw_c in cand:
                c = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", raw_c).strip()
                if not c:
                    continue
                sm = _CGPA_RE.search(c) or _PCT_RE.search(c)
                if sm and not score:
                    cleaned = _CGPA_RE.sub("", _PCT_RE.sub("", c))
                    cleaned = cleaned.strip(" |;\u00b7-")
                    # a bare scale fragment left over after stripping the
                    # tag ('CGPA: 9.07' + '/10') means the candidate IS the
                    # full score tag - keep it whole (Vinod: the truncated
                    # 'CGPA: 9.07' otherwise renders in the rail while the
                    # full 'CGPA: 9.07/10' survives in meta -> shown twice)
                    if re.fullmatch(r"/\s*\d+(?:\.\d+)?", cleaned or ""):
                        cleaned = ""
                    # a candidate that is ONLY the score tag gets the FULL
                    # tag as the display score ('CGPA: 9.07/10', not the
                    # regex's truncated 'CGPA: 9.07'); a longer line keeps
                    # the short match as its score while the rest of the
                    # line continues through the degree/school checks
                    score = c if not cleaned else sm.group(0).strip()
                    if not cleaned:
                        continue
                    c = cleaned
                if _DEG_RE.search(c) and not degree:
                    degree = c
                elif _SCHOOL_RE.search(c) and not school:
                    head, _, tail = c.rpartition(", ")
                    if tail and _LOC_LINE_RE.fullmatch(tail) and not location:
                        school, location = head, tail
                    else:
                        school = c
                elif _LOC_LINE_RE.fullmatch(c) and not location and len(c) <= 32:
                    location = c
            # nothing consumable this pass -> carry the previous pass's
            # fields through untouched (shaper must be re-runnable)
            if not any((school, degree, location, score)) and prev_edu:
                school = _html.unescape(prev_edu.get("school") or "")
                degree = _html.unescape(prev_edu.get("degree") or "")
                location = _html.unescape(prev_edu.get("location") or "")
                score = _html.unescape(prev_edu.get("score") or "")
            # DISPLAY form drops the '/10' suffix ('CGPA: 9.07/10' -> 'CGPA:
            # 9.07'); percentages keep their % sign (user spec).
            display = _display_score(score)
            consumed = {degree, school, location, score}
            e["edu"] = {
                "school": _html.escape(school),
                "degree": _html.escape(degree),
                "location": _html.escape(location),
                "score": _html.escape(score),
                "score_display": _html.escape(display),
                # bullets the shaper did NOT consume stay as bullets
                "bullets": [_bold_metrics(b) for b in e.get("bullets", [])
                            if b not in consumed],
            }
            # consumed lines never render twice: the entry's own bullet list
            # drops them (Mode B renders e["bullets"])
            e["bullets"] = [b for b in e.get("bullets", [])
                            if b not in consumed]
            # meta rebuild: drop ONLY the part that was consumed AS the
            # score (it renders right-aligned); school/degree/location
            # parts stay in meta because Mode B renders them inline
            if meta_parts:
                kept = [p for p in meta_parts
                        if p.strip() and p.strip() != score]
                e["meta"] = "; ".join(kept) if kept else ""
            # compact the rendered date ('September 2022-Present' ->
            # 'Sep 2022-Present'): the full month name wraps the row-1
            # right cell to two lines (Kanish).  Abbreviations are
            # idempotent, so re-running the shaper is safe.
            if e.get("date"):
                e["date"] = _compact_date(e["date"])
    return sections

# --- vendored icon/bullet fonts (B.4/B.5) ------------------------------------
# Font Awesome Free (solid + brands) provides header contact icons; DejaVu
# Sans carries proper Unicode bullet markers (xhtml2pdf's Helvetica default
# renders U+2022 as a hollow square).  All files live in backend/fonts/.
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
_FONT_FILES = {
    # registry key -> (file name, CSS family name)
    "solid":  ("fa-solid-900.ttf", "font-awesome-solid"),
    "brands": ("fa-brands-400.ttf", "font-awesome-brands"),
    "dejavu": ("DejaVuSans.ttf", "resume-unicode"),
    # Computer Modern Unicode (CMU Serif) - the LaTeX/academic-CV look of
    # the Kanish/Sarthak/Vikas reference resumes (CMR10/CMBX10 embedded
    # there).  Vendored under backend/fonts/ (GUST Font License, free).
    # Distinct family per weight because xhtml2pdf resolves <strong>/<b>
    # through CSS selectors, not reportlab weight mappings (probed: the
    # addMapping route falls back to Helvetica; the selector route embeds
    # the real CMU Bold).
    "cmu-r":  ("cmunrm.ttf", "cmu-serif"),
    "cmu-b":  ("cmunbx.ttf", "cmu-serif-b"),
    "cmu-i":  ("cmunti.ttf", "cmu-serif-i"),
    "cmu-bi": ("cmunbi.ttf", "cmu-serif-bi"),
}
_FA_GLYPHS = {
    # contact kind -> (registry key, unicode codepoint)
    "email":      ("solid",  0xF0E0),
    "phone":      ("solid",  0xF095),
    "github":     ("brands", 0xF09B),
    "gitlab":     ("brands", 0xF296),
    "linkedin":   ("brands", 0xF0E1),      # linkedin-in mark
    "leetcode":   ("solid",  0xF121),      # no FA brand glyph -> </> code
    "hackerrank": ("solid",  0xF121),
    "kaggle":     ("solid",  0xF080),
    "blog":       ("solid",  0xF09E),      # rss
    "vsext":      ("solid",  0xF12E),      # puzzle piece
    "portfolio":  ("solid",  0xF0AC),      # globe
    "demo":       ("solid",  0xF0C1),      # link
    "behance":    ("brands", 0xF1B4),
    "web":        ("solid",  0xF0AC),
}


def available_fonts() -> dict:
    """Vendored fonts actually on disk (key -> abs path); empty when the
    backend/fonts folder is missing/stripped -> graceful ASCII fallback."""
    out = {}
    for key, (fname, _fam) in _FONT_FILES.items():
        p = os.path.join(FONTS_DIR, fname)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 10000:
                out[key] = p
        except OSError:
            continue
    return out


def has_icon_fonts() -> bool:
    av = available_fonts()
    return "solid" in av and "brands" in av


# Bullet rendering strategy (B.5).  Auto order: DejaVu available ->
# native <ul>/<li> whose markers inherit the TTF via
# ``frag.bulletFontName = tt2ps(family)``; otherwise ASCII hyphens.
# Tests may force "span" (list-style:none + styled marker span) through
# set_bullet_mode() - used by the visual gate if native fails pixels.
BULLET_MODE_OVERRIDE = {"v": None}


def _bullet_mode() -> str:
    if BULLET_MODE_OVERRIDE["v"]:
        return BULLET_MODE_OVERRIDE["v"]
    if "dejavu" not in available_fonts():
        return "ascii"
    # WeasyPrint draws <ul> list markers with the li's font (cmu-serif), NOT
    # the ul's resume-unicode; U+2022 does not exist in Computer Modern, so
    # the marker mis-maps to a stray glyph ("Î"/"9"/"Â").  The span branch
    # always draws the marker explicitly with the DejaVu family -> correct
    # bullet on both engines.  xhtml2pdf keeps the native <ul> branch (its
    # bulletFontName mapping works and pixel tests pass).
    return "span" if _HAS_WEASYPRINT else "native"


def set_bullet_mode(mode: str | None) -> None:
    """Force a bullet strategy: 'native' | 'span' | 'ascii' | None(auto)."""
    assert mode in (None, "native", "span", "ascii")
    BULLET_MODE_OVERRIDE["v"] = mode


def font_face_css() -> str:
    """@font-face rules for the vendored TTFs ('' when files are missing).

    xhtml2pdf wants a plain local path (its bridge stats the file); WeasyPrint
    resolves url() against the string document's base URL, so it needs an
    absolute file:// URL - otherwise the CMU fonts silently fall back to the
    system default (DejaVu on Linux) and the PDF loses its LaTeX look.
    """
    if not available_fonts():
        return ""
    fams = {_FONT_FILES[k][1]: p for k, p in available_fonts().items()}
    if _HAS_WEASYPRINT:
        return "\n".join(
            "@font-face { font-family: \"%s\"; src: url('file:///%s'); }"
            % (fam, path.replace("\\", "/").lstrip("/"))
            for fam, path in fams.items())
    return "\n".join(
        "@font-face { font-family: \"%s\"; src: url('%s'); }"
        % (fam, path.replace("\\", "/")) for fam, path in fams.items())


def install_xhtml2pdf_font_bridge() -> bool:
    """Patch xhtml2pdf so vendored TTFs embed correctly on Windows.

    Upstream ``pisaContext.loadFont`` copies the TTF into a
    NamedTemporaryFile and then asks reportlab to RE-open that path while
    the create-handle is still alive -> PermissionError on Windows.  The
    bridge short-circuits sources pointing at a real local file and
    registers them with reportlab directly (same family-alias bookkeeping);
    everything else falls through to the original implementation.
    """
    try:
        from xhtml2pdf.context import pisaContext
    except Exception:
        return False
    if getattr(pisaContext, "_rf_font_bridge", False):
        return True

    def loadFont(self, names, src, encoding="WinAnsiEncoding",
                 bold=0, italic=0):
        try:
            file = src
            uri = getattr(file, "uri", None) or (src if isinstance(
                src, str) else "")
            if isinstance(uri, str) and uri.lower().endswith((".ttf", ".ttc")) \
                    and os.path.isfile(uri):
                if isinstance(names, list):
                    alias = [str(x) for x in names]
                else:
                    alias = [str(x).strip()
                             for x in str(names).split(",") if x.strip()]
                fname = alias[0] if alias else "embeddedfont"
                full = "%s_%d%d" % (fname, bold, italic)
                if full not in self.fontList:
                    from reportlab.lib.fonts import addMapping
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    pdfmetrics.registerFont(TTFont(full, uri))
                    for b in (0, 1):
                        for i in (0, 1):
                            addMapping(fname, b, i, full)
                    self.registerFont(fname, [*alias, full])
                return None
        except Exception:
            pass  # never break rendering - fall back to upstream behaviour
        return pisaContext.__dict__["_orig_loadFont"](
            self, names, src, encoding=encoding, bold=bold, italic=italic)

    pisaContext._orig_loadFont = pisaContext.loadFont
    pisaContext.loadFont = loadFont
    pisaContext._rf_font_bridge = True
    return True


try:
    from weasyprint import HTML as _WeasyHTML  # noqa: N813
    _HAS_WEASYPRINT = True
except Exception:  # noqa: BLE001  (missing GTK DLLs etc.)
    _HAS_WEASYPRINT = False


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )


def render_html(resume: dict, template_name: str = "classic",
                compact: int = 0) -> str:
    """Structured resume JSON -> HTML.  Works on a DEEP COPY: the entry-prep
    pipeline (education shaping, link extraction) mutates entries, and this
    function runs once per tightening attempt inside generate_pdf - without
    the copy the 2nd attempt operates on pre-consumed data and loses
    education scores / link fields (Vinod regression)."""
    resume = copy.deepcopy(resume)
    if template_name == "auto":
        name = auto_template(resume)
    elif template_name in AVAILABLE_TEMPLATES:
        name = template_name
    else:
        name = "classic"
    tpl = _env().get_template("%s.html" % name)
    contact_items = _contact_items(resume.get("contacts", []))
    install_xhtml2pdf_font_bridge()
    fonts_av = available_fonts()
    icons_on = has_icon_fonts()
    # Monochrome icon (real FA glyph when vendored, legacy letter otherwise)
    # + short clickable label per contact; the URL lives only in href.
    parts = []
    for it in contact_items:
        if icons_on:
            fkey, cp = _FA_GLYPHS.get(it["kind"], ("solid", 0xF0AC))
            fam = _FONT_FILES[fkey][1]
            chip = ("<span class=\"ico\" style=\"font-family:'%s'\">&#x%x;"
                    "</span>" % (fam, cp))
        else:
            chip = "<span class=\"ico\">%s</span>" % _html.escape(
                it["glyph"])
        body = it["label"]
        if it["href"]:
            body = "<a class=\"clink\" href=\"%s\">%s</a>" % (it["href"],
                                                              it["label"])
        parts.append("%s %s" % (chip, body))
    contacts_html = Markup(" &nbsp;&nbsp; ".join(parts)) if parts else ""
    sections = [s for s in resume.get("sections", [])
                if s.get("type") != "entries" or s.get("entries")]
    sections = _order_sections(sections)
    sections = _merge_location_entries(sections)
    sections = _shape_education(sections)
    sections = _prep_skills(sections)
    sections = _prep_entries(sections)
    levels = _levels_for(name)
    preset = levels[max(0, min(compact, len(levels) - 1))]
    return tpl.render(
        name=resume.get("name") or "Your Name",
        headline=resume.get("headline", ""),
        contacts=resume.get("contacts", []),
        contact_items=contact_items,
        contacts_html=contacts_html,
        sections=sections,
        lh=preset["lh"], fs=preset["fs"], h2m=preset["h2m"],
        em=preset["em"], name_fs=preset["name_fs"],
        compact=compact,
        # B.4/B.5 hooks: '' when backend/fonts is absent -> templates keep
        # working unchanged.  Markup() so quotes survive autoescaping.
        font_css=Markup(font_face_css()),
        icon_fonts=icons_on,
        bmark_mode=_bullet_mode(),
    )


# Spacing presets.  Level 0 is COMFORTABLE by default (bullets ~1.45
# line-height, clear project separation) matching the reference resumes;
# tightening is a last resort driven by the one-page limiter, not the default.
_COMPACT_LEVELS = [
    {"lh": "1.45", "h2m": "16px 0 6px 0", "em": "10px", "fs": "10pt",
     "name_fs": "18pt"},
    {"lh": "1.25", "h2m": "10px 0 4px 0", "em": "6px", "fs": "9.8pt",
     "name_fs": "16pt"},
    {"lh": "1.12", "h2m": "7px 0 3px 0", "em": "4px", "fs": "9.5pt",
     "name_fs": "15pt"},
]

# Mode A (cv_academic) presets: the TIGHT academic-CV density of Kanish's /
# Sarthak's LaTeX-style originals - realistic one-pager content fits a single
# page at readable size without dropping below ~9.5pt.
_ACADEMIC_LEVELS = [
    {"lh": "1.18", "h2m": "13px 0 4px 0", "em": "5px", "fs": "10pt",
     "name_fs": "16pt"},
    {"lh": "1.12", "h2m": "10px 0 3px 0", "em": "4px", "fs": "9.8pt",
     "name_fs": "15pt"},
    {"lh": "1.06", "h2m": "8px 0 2px 0", "em": "3px", "fs": "9.5pt",
     "name_fs": "14pt"},
]


def _levels_for(template_name: str) -> list:
    return _ACADEMIC_LEVELS if template_name == "cv_academic" \
        else _COMPACT_LEVELS


def _page_count(pdf_bytes: bytes) -> int:
    import fitz
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n = doc.page_count
        doc.close()
        return n
    except Exception:  # noqa: BLE001 - never fail generation on counting
        return 1


# A trailing page carrying less than this much content is an ORPHAN fragment
# (a couple of spilled bullets) rather than a genuine content page.  ~6 lines
# at floor spacing; Ashmit's 2 orphaned Achievements bullets measure 24.9pt.
_ORPHAN_TAIL_MAX_PT = 72.0


def _has_orphan_tail(pdf_bytes: bytes) -> bool:
    """True when the LAST page holds only a tiny orphan fragment."""
    import fitz
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count <= 1:
            doc.close()
            return False
        rows = []
        for blk in doc[doc.page_count - 1].get_text("dict")["blocks"]:
            for line in blk.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                y0 = min(s["bbox"][1] for s in spans)
                y1 = max(s["bbox"][3] for s in spans)
                rows.append((y0, y1))
        doc.close()
        if not rows:
            return True  # an EMPTY trailing page is the worst orphan
        return (max(y1 for y0, y1 in rows)
                - min(y0 for y0, y1 in rows)) <= _ORPHAN_TAIL_MAX_PT
    except Exception:  # noqa: BLE001 - never fail generation on measuring
        return False


def generate_pdf(resume: dict, template_name: str = "classic",
                 out_path: str | None = None,
                 max_pages: int = 1) -> bytes:
    """Render resume JSON into a clean PDF. Returns bytes; optionally saves.

    HARD ONE-PAGE LIMIT: if the render exceeds ``max_pages``, re-render with
    progressively tighter spacing (margins -> line-height -> font size) until
    it fits or the readability floor is reached; a warning is logged when the
    content genuinely cannot fit on one page.

    ``max_pages`` > 1 (original upload was a genuine multi-page resume):
    a render within ``max_pages`` is accepted at the COMFORTABLE preset
    unless its trailing page is a near-empty ORPHAN fragment (a couple of
    spilled bullets) - in that case the ladder keeps tightening, never
    below the readability floor (last preset), to try to pull the fragment
    up.  If even the floor cannot reduce the page count, the comfortable
    multi-page output ships unchanged: content is preserved at full
    readable font size, never crushed for a cosmetic page saving.
    """
    pdf = b""
    used = 0
    last_pages = 0
    # Resolve the two-mode automatic selection once so every tightening
    # attempt renders with the SAME template identity.
    if template_name == "auto":
        template_name = auto_template(resume)
    elif template_name not in AVAILABLE_TEMPLATES:
        template_name = "classic"
    levels = _levels_for(template_name)
    first_candidate = None   # most-comfortable attempt exceeding max_pages
    first_ok = None          # (pdf, level, pages) first within max_pages
    fewest = None            # (pdf, level, pages) fewest pages at/below floor
    for level, preset in enumerate(levels):
        html = render_html(resume, template_name, compact=level)
        candidate = html_to_pdf_bytes(html)
        pages = _page_count(candidate)
        last_pages = pages
        if pages > max_pages and first_candidate is None:
            first_candidate = candidate
        if pages <= max_pages:
            if fewest is None or pages < fewest[2]:
                fewest = (candidate, level, pages)
            if pages == 1:
                pdf, used = candidate, level
                break
            if first_ok is None:
                first_ok = (candidate, level, pages)
                # multi-page result: a near-empty trailing page is an
                # orphan fragment - keep tightening (the ladder itself
                # ends at the 9.5pt/1.06 readability floor) to try to
                # pull it onto the previous page before settling for
                # comfortable multi-page output.
                if not _has_orphan_tail(candidate):
                    pdf, used = candidate, level
                    break
    if not pdf:
        if fewest is not None and first_ok is not None \
                and fewest[2] < first_ok[2]:
            # tightening (within the floor) reduced the page count - use it
            pdf, used = fewest[0], fewest[1]
        elif first_ok is not None:
            # multi-page is genuine: comfortable output, no warning
            pdf, used = first_ok[0], first_ok[1]
        else:
            # Content genuinely exceeds the page limit even at the
            # readability floor - ship the COMFORTABLE multi-page output
            # at full font size instead of the most-cramped attempt
            # (Sarthak: 2 pages @ 9.5pt with crushed line-height was the
            # previous behaviour).
            if first_candidate is not None:
                pdf, used = first_candidate, 0
            print("[one-page-limit] WARNING: still %d page(s) after "
                  "tightening to %.1fpt - content exceeds the limit; "
                  "shipping multi-page output at readable spacing."
                  % (last_pages or max_pages, 10.0), file=sys.stderr)
    if out_path:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(pdf)
    return pdf


def html_to_pdf_bytes(html: str) -> bytes:
    if _HAS_WEASYPRINT:
        return _WeasyHTML(string=html).write_pdf()
    return _xhtml2pdf_bytes(html)


def _xhtml2pdf_bytes(html: str) -> bytes:
    from xhtml2pdf import pisa
    buf = io.BytesIO()
    result = pisa.CreatePDF(io.StringIO(html), dest=buf, encoding="utf-8")
    if result.err:
        raise RuntimeError("xhtml2pdf failed with %d error(s)" % result.err)
    return buf.getvalue()
