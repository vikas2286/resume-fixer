"""Gemini LLM service: bullet rewriting, red-flag detection, JD matching.

Every function degrades gracefully: if GEMINI_API_KEY is missing, the SDK is
unavailable, or the call fails/times out, callers fall back to built-in
rule-based versions so the core demo flow never breaks live.
"""
from __future__ import annotations

import json
import os
import re
import time
import concurrent.futures as cf

# Load environment (.env) so GEMINI_API_KEY / GEMINI_MODEL are picked up when
# running `uvicorn main:app` without a manual export. Pin to THIS backend dir
# so we never accidentally pick up a stray .env in a parent directory.
try:
    from dotenv import load_dotenv
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_THIS_DIR, ".env"))
except Exception:  # python-dotenv optional — env still works via real exports
    pass

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or ""
# Users often paste an OAuth token bundle ("AQ....,AIzaSy...,AIzaSy...")
# instead of a single API key. If a real API key (AIza...) is embedded,
# pull out the FIRST one; otherwise use the raw value trimmed.
_m = re.search(r"AIza[0-9A-Za-z_\-]{30,}", GEMINI_API_KEY)
if _m:
    GEMINI_API_KEY = _m.group(0)
else:
    GEMINI_API_KEY = GEMINI_API_KEY.strip().strip('"').strip("'")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
TIMEOUT_S = int(os.environ.get("GEMINI_TIMEOUT", "60"))
# Boot diagnostics: confirm .env GEMINI_MODEL is actually read (the resolved
# model HANDLE is logged when _get_model() first builds it).
print("[llm] configured model from .env/env: %r" % MODEL_NAME, flush=True)
# Cap for honoring the API's 'retry in Xs' backoff on a 429/quota error.  Keeps
# the demo snappy: if the window exceeds this we fall back to rules instead of
# blocking the request for minutes.
RETRY_MAX_S = 40.0

# Background executor so a hung generate_content() call can never block the
# FastAPI event loop / request thread beyond TIMEOUT_S.
_EXECUTOR = cf.ThreadPoolExecutor(max_workers=2)

_model = None
_tried = False
_MODEL_CACHE = None


def gemini_available() -> bool:
    _get_model()
    return _model is not None


def _available_models():
    """Model ids that support generateContent (cached per process)."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        try:
            import google.generativeai as genai
            out = []
            for m in genai.list_models():
                methods = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" in methods:
                    out.append(m.name.replace("models/", ""))
            _MODEL_CACHE = out
        except Exception as e:  # noqa: BLE001
            print("[llm] list_models failed: %s" % e)
            _MODEL_CACHE = []
    return _MODEL_CACHE


def _resolve_model_name():
    """Return MODEL_NAME if the key can use it, else the best available."""
    avail = _available_models()
    if not avail:
        return MODEL_NAME
    if MODEL_NAME in avail:
        return MODEL_NAME
    # Stable aliases first, then newest *flash* text model as last resort.
    for pref in ("gemini-flash-latest", "gemini-2.5-flash", "gemini-pro-latest"):
        if pref in avail:
            print("[llm] %r unavailable - falling back to %r"
                  % (MODEL_NAME, pref))
            return pref
    skip = ("tts", "image", "robotics", "embedding", "lyria", "banana",
            "computer-use", "deep-research", "omni")
    cands = [m for m in avail if "flash" in m and not any(s in m for s in skip)]
    name = sorted(cands)[-1] if cands else avail[0]
    print("[llm] %r unavailable - using %r" % (MODEL_NAME, name))
    return name


def _get_model():
    global _model, _tried
    if _tried:
        return _model
    _tried = True
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(_resolve_model_name())
        print("[llm] resolved model handle: %s" % _model.model_name, flush=True)
    except Exception as e:  # noqa: BLE001
        print("[llm] Gemini unavailable: %s" % e)
        _model = None
    return _model


def _switch_model(new_name):
    """Rebuild the model handle on a different Gemini model id."""
    global _model
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(new_name)
        print("[llm] switched model to %r" % new_name)
    except Exception as e:  # noqa: BLE001
        print("[llm] model switch to %r failed: %s" % (new_name, e))


def _ask(prompt: str):
    """One generation call with a quota-aware same-model retry.

    On a 429/quota error (the API's message carries 'retry in Xs'):
      1. honor the backoff and retry the SAME pinned model (never a
         different/unpinned model - those may themselves be quota-exhausted,
         e.g. the Pro aliases with limit=0);
      2. only if that retry fails too, fall back (caller uses rules).
    Any other error goes straight to fallback.
    """
    model = _get_model()
    if model is None:
        return None

    def _one_shot(m):
        fut = _EXECUTOR.submit(lambda mm=m: mm.generate_content(prompt))
        return fut.result(timeout=TIMEOUT_S)

    try:
        resp = _one_shot(model)
        return (resp.text or "").strip()
    except cf.TimeoutError:
        print("[llm] call timed out after %ss - using fallback" % TIMEOUT_S)
        return None
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        # 429 / quota-exhausted: honor the API's own backoff, retry SAME model.
        m = re.search(r"retry in ([\d.]+)\s*s", msg)
        if m:
            wait = min(float(m.group(1)) + 1.0, RETRY_MAX_S)
            print("[llm] quota/rate-limit (%s) - waiting %.1fs, "
                  "retrying same model %s"
                  % (msg[:80], wait, getattr(model, "model_name", "?")),
                  flush=True)
            time.sleep(wait)
            try:
                resp = _one_shot(model)
                return (resp.text or "").strip()
            except cf.TimeoutError:
                print("[llm] retry after backoff timed out - using fallback")
                return None
            except Exception as e2:  # noqa: BLE001
                print("[llm] retry after backoff also failed (%s) - "
                      "using fallback" % str(e2)[:160])
                return None
        print("[llm] call failed: %s - using fallback" % msg[:200])
        return None


def _ask_json(prompt: str):
    raw = _ask(prompt)
    if not raw:
        return None
    m = re.search(r"\{.*\}|\[.*\]", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ------------------------------------------------------- summary bolding

def summary_key_phrases(text: str):
    """C.8: pick 3-5 key noun phrases in the Summary to bold.  Returns a
    list of verbatim phrases, or None when unavailable (no key, API error,
    timeout, unusable answer).  The caller falls back to rule-based metric
    bolding on None."""
    if not (text or "").strip():
        return None
    prompt = (
        "You are an expert resume writer. Below is the Summary section of a "
        "resume. Pick 3 to 5 of the MOST impactful noun phrases (core "
        "technologies, skills, achievements) that a recruiter should notice "
        "first.\n"
        "Rules: each phrase must appear VERBATIM in the summary; each 2-6 "
        "words long; no duplicates; return ONLY a JSON array of strings, "
        "nothing else.\n\nSummary:\n" + text.strip()[:900])
    data = _ask_json(prompt)
    if not isinstance(data, list):
        return None
    low = text.lower()
    out, seen = [], set()
    for p in data:
        if not isinstance(p, str):
            continue
        p = p.strip()
        if (not p or len(p) > 60 or p.lower() in seen
                or p.lower() not in low):
            continue
        seen.add(p.lower())
        out.append(p)
        if len(out) >= 5:
            break
    return out or None


# ---------------------------------------------------------------- rewrite

def rewrite_bullet(bullet: str, context: str = ""):
    """Return a stronger version of one resume bullet, or None on failure."""
    prompt = (
        "Rewrite this resume bullet point to be professional, active-voice, and "
        "impact-driven. Start with a strong action verb, keep it under 30 words, "
        "do NOT invent facts or numbers. Reply with ONLY the rewritten bullet.\n\n"
        + ("Context: %s\n" % context if context else "")
        + "Bullet: %s" % bullet
    )
    out = _ask(prompt)
    return out.strip('"') if out else None


def rewrite_bullets(bullets: list, context: str = ""):
    """Rewrite many bullets; returns list aligned with input (None per failure)."""
    if not bullets:
        return []
    prompt = (
        "You are an expert resume writer. Rewrite EACH numbered resume bullet to "
        "be professional, active-voice, and impact-driven (strong verb first, "
        "under 30 words). Do not invent facts.\n"
        'Return ONLY a JSON object: {"rewrites": {"1": "...", "2": "..."}}\n\n'
        + ("Context: %s\n" % context if context else "")
        + "\n".join("%d. %s" % (i + 1, b) for i, b in enumerate(bullets))
    )
    data = _ask_json(prompt)
    if not isinstance(data, dict):
        return [None] * len(bullets)
    mapping = data.get("rewrites", {})
    out = []
    for i, b in enumerate(bullets):
        r = mapping.get(str(i + 1)) or mapping.get(i + 1)
        out.append(str(r).strip() if r else None)
    return out


# ---------------------------------------------------------------- red flags

CLICHES = [
    "hard worker", "hard working", "team player", "go-getter",
    "think outside the box", "detail oriented", "detail-oriented",
    "self-starter", "results-driven", "results driven", "go-to person",
    "wears many hats", "hit the ground running", "synergy", "guru",
    "ninja", "rockstar", "rock star", "passionate about excellence",
]

PASSIVE_PATTERNS = [
    r"\bwas responsible for\b", r"\bwere responsible for\b",
    r"\bwas involved in\b", r"\bduties included\b", r"\btasked with\b",
    r"\bhelped (?:to )?(?:with|in)\b",
]


def rule_based_red_flags(resume_text: str) -> list:
    """Deterministic fallback: cliches, passive voice, missing metrics."""
    flags = []
    lines = [l for l in resume_text.split("\n") if l.strip()]

    for phrase in CLICHES:
        for line in lines:
            if phrase in line.lower():
                flags.append({
                    "type": "cliche",
                    "quote": line.strip()[:140],
                    "issue": 'Cliche phrase "%s" - recruiters skim right past it.' % phrase,
                    "fix": "Replace with a concrete achievement.",
                })
                break

    for pat in PASSIVE_PATTERNS:
        for line in lines:
            if re.search(pat, line, re.IGNORECASE):
                flags.append({
                    "type": "passive_voice",
                    "quote": line.strip()[:140],
                    "issue": "Passive voice - weakens ownership of the achievement.",
                    "fix": "Start with an action verb: Led, Built, Cut, Grew...",
                })
                break

    bullet_lines = [l for l in lines if l.strip().startswith(("-", "\u2022", "*"))]
    if bullet_lines:
        no_metric = [l for l in bullet_lines if not re.search(r"\d", l)]
        if len(no_metric) > len(bullet_lines) * 0.5:
            flags.append({
                "type": "missing_metrics",
                "quote": no_metric[0].strip()[:140],
                "issue": "%d of %d bullets contain no numbers/metrics."
                         % (len(no_metric), len(bullet_lines)),
                "fix": "Quantify impact: %, $, time saved, users served.",
            })
    return flags


def detect_red_flags(resume_text: str) -> list:
    """LLM detection with rule-based fallback."""
    prompt = (
        "Analyze this resume for weak content. Find:\n"
        "1. cliche phrases, 2. passive voice, 3. bullets missing metrics/numbers.\n"
        'Return ONLY JSON array: [{"type":"cliche|passive_voice|missing_metrics",'
        '"quote":"exact quote","issue":"why it hurts","fix":"suggestion"}]\n\n'
        "RESUME:\n%s" % resume_text[:6000]
    )
    data = _ask_json(prompt)
    if isinstance(data, list) and data:
        return [
            {
                "type": str(d.get("type", "cliche")),
                "quote": str(d.get("quote", ""))[:200],
                "issue": str(d.get("issue", "")),
                "fix": str(d.get("fix", "")),
            }
            for d in data
            if isinstance(d, dict)
        ]
    return rule_based_red_flags(resume_text)


# ---------------------------------------------------------------- JD match

STOPWORDS = set("""a an the and or but if then than that this these those with without
for from to of in on at by as is are was were be been being it its will would can could
should have has had do does did not no you your we our they their he she his her i me my
about into over under out up down off above below between among through during before
after while what which who whom whose when where why how all any both each few more most
other some such only own same so too very just also may might must shall using use used
role job position candidate ideal looking join you'll responsibilities requirements
preferred plus etc strong ability able across well work working team teams years year new
company companies experience including include includes must nice good great excellent""".split())


def rule_based_jd_match(resume_text: str, jd_text: str) -> dict:
    """Deterministic keyword gap analysis fallback."""
    def keywords(text):
        words = re.findall(r"[a-zA-Z][a-zA-Z+#./-]{1,}", text.lower())
        seen = {}
        for w in words:
            w = w.strip(".-")
            if len(w) >= 3 and w not in STOPWORDS:
                seen[w] = seen.get(w, 0) + 1
        return seen

    jd_kw = keywords(jd_text)
    resume_low = " " + re.sub(r"\s+", " ", resume_text.lower()) + " "
    matched, missing = [], []
    ranked = sorted(jd_kw.items(), key=lambda kv: -kv[1])
    for kw, freq in ranked[:60]:
        item = {"keyword": kw, "frequency": freq}
        (matched if kw in resume_low else missing).append(item)
    top = min(60, max(1, len(ranked)))
    score = round(len(matched) / top * 100)
    return {"match_score": score, "matched": matched[:25], "missing": missing[:25],
            "engine": "rules"}


def match_jd(resume_text: str, jd_text: str) -> dict:
    """LLM JD matching with deterministic fallback."""
    prompt = (
        "Compare this resume against the job description. Extract the important "
        "keywords/skills from the JD, then classify which appear in the resume.\n"
        'Return ONLY JSON: {"matched":["kw",...],"missing":["kw",...]}\n'
        "Max 25 items per list.\n\nJOB DESCRIPTION:\n%s\n\nRESUME:\n%s"
        % (jd_text[:4000], resume_text[:4000])
    )
    data = _ask_json(prompt)
    if isinstance(data, dict) and ("matched" in data or "missing" in data):
        matched = [{"keyword": str(k)} for k in (data.get("matched") or [])][:25]
        missing = [{"keyword": str(k)} for k in (data.get("missing") or [])][:25]
        total = len(matched) + len(missing)
        score = round(len(matched) / total * 100) if total else 0
        return {"match_score": score, "matched": matched, "missing": missing,
                "engine": "gemini"}
    return rule_based_jd_match(resume_text, jd_text)


# ---------------------------------------------------------------- structuring

def structure_resume(raw_text: str):
    """Use Gemini to convert messy resume text into clean structured JSON.

    Returns dict or None (caller falls back to heuristic parser output).
    Shape: {name, headline, contacts:[], sections:[{title,type,...}]}
      type=paragraph -> {text}; type=skills -> {items:[]};
      type=entries   -> {entries:[{title,meta,date,bullets:[]}]}
    """
    prompt = (
        "Convert this messy resume text into clean structured JSON.\n"
        "Shape:\n"
        '{"name":"","headline":"","contacts":[],'
        '"sections":[{"title":"Experience","type":"entries","entries":'
        '[{"title":"","meta":"company/location","date":"","bullets":[""]}]}, '
        '{"title":"Skills","type":"skills","items":[""]}, '
        '{"title":"Summary","type":"paragraph","text":""}]}\n'
        "Section order: Summary, Experience, Education, Skills, Projects, "
        "Certifications. Do NOT invent content that is not present.\n"
        "Return ONLY the JSON object.\n\nRESUME TEXT:\n%s" % raw_text[:8000]
    )
    data = _ask_json(prompt)
    if isinstance(data, dict) and isinstance(data.get("sections"), list):
        data.setdefault("name", "")
        data.setdefault("headline", "")
        data.setdefault("contacts", [])
        return data
    return None
