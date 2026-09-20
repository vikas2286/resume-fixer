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
#
# Deterministic safety net for AI rewrites: the prompt forbids fabricated
# numbers, but LLMs still slip (a "6" for a 7-item list, "3+ blogs weekly"
# for a bullet that just says 'reading tech blogs').  These helpers catch
# the mechanical cases so a rewritten bullet can never contain a number
# that isn't in the source, countable from its own enumeration, or a
# duration derived from the entry's date range.

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_DURATION_RE = re.compile(
    r"\b\d+(?:\.\d+)?[\s\-]{0,3}(?:week|month|day|year)s?\b", re.I)
_ENUM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s+[^.;]{0,60}?"
    r"(?:including|such as|like|supporting|covering|comprising|featuring|:)"
    r"\s+([^.;;]+)", re.I)


def _enum_items(tail: str):
    """List items inside an enumeration tail (post-trigger text).

    Drops any trailing clause introduced by an em/en dash ('...Busbars—at
    the 400/220 kV facility' - the location is not a list item) and any
    fragment that carries no letters (pure number fragments from slashed
    specs like '400/220' are not items).
    """
    tail = re.split(r"[\u2013\u2014]", tail)[0]
    # Trailing temporal/scope clauses are not list items ('...including CTs
    # and CVTs, during a 1-month internship' lists 2 components, not 3).
    tail = re.split(r",?\s+\b(?:during|across|within|throughout)\b", tail)[0]
    return [i for i in re.split(r",|/|\band\b", tail)
            if i.strip() and re.search(r"[A-Za-z]", i)]


def _fix_enum_counts(new: str) -> str:
    """'6 components including A, B, C' with 3 items -> count corrected.

    A rewrite may attach a count to an enumeration; the count must match
    the number of items actually listed (or exceed it only as 'N+').  When
    the model miscounts, repair it from its own list.
    """
    def _fix(m):
        n = float(m.group(1))
        items = _enum_items(m.group(2))
        if not items or n == len(items):
            return m.group(0)
        if len(items) == 1:
            return re.sub(_NUM_RE, "one", m.group(0), count=1)
        return re.sub(_NUM_RE, str(len(items)), m.group(0), count=1)
    return _ENUM_RE.sub(_fix, new)


def _approx_counts_grounding(new: str, source: str):
    """Enumerated item counts available as grounding for approximate numbers.

    Aggressive mode may convert a vague scope word ('multiple', 'several')
    into a number ONLY when that number is inferable from an enumerated
    list in the rewrite itself or the surrounding source text.  Returns
    the list of grounded item counts (empty = no grounding at all).
    """
    counts = []
    for m in _ENUM_RE.finditer(new + " " + source):
        c = len(_enum_items(m.group(2)))
        if c:
            counts.append(c)
    return counts


def _swap_weak_opener(bullet: str):
    """Deterministic last-resort: replace a banned weak opener with a strong
    verb.  Pure wording swap - the rest of the sentence is untouched, so no
    fabrication risk - used only when a guarded rewrite could not be
    produced and the ORIGINAL would otherwise keep a passive opener."""
    for pat, verb in _WEAK_OPENER_SWAPS:
        m = pat.match(bullet)
        if m:
            return verb + " " + bullet[m.end():].strip()
    return None


_WEAK_OPENER_SWAPS = [
    (re.compile(r"^gained (?:hands-on |practical |direct |valuable )?exposure to", re.I),
     "Investigated"),
    (re.compile(r"^gained (?:practical |hands-on |valuable )?(?:insights?|understanding|knowledge) (?:into|of|about)", re.I),
     "Analyzed"),
    (re.compile(r"^learned about", re.I), "Examined"),
    (re.compile(r"^observed and understood\b", re.I), "Assessed"),
    (re.compile(r"^observed\b", re.I), "Monitored"),
    (re.compile(r"^acquired (?:an?|comprehensive) (?:understanding|knowledge|grasp) of", re.I),
     "Analyzed"),
    (re.compile(r"^contributed to (?:the )?understanding of", re.I), "Examined"),
    (re.compile(r"^contributed to", re.I), "Advanced"),
    (re.compile(r"^was (?:involved|responsible) (?:in|for)", re.I), "Managed"),
    (re.compile(r"^worked on", re.I), "Executed"),
    (re.compile(r"^assisted (?:with|in)", re.I), "Supported"),
    (re.compile(r"^helped (?:with|in|to)", re.I), "Supported"),
]


def _has_fabricated_number(new: str, bullet: str, context: str,
                           aggressive: bool = False) -> bool:
    """True when the rewrite contains a number with no legitimate source.

    STRICT (default) mode: allowed numbers are those present in the bullet
    or context, counts verified against their own enumeration (post
    _fix_enum_counts), and durations ('4-week internship') derived from the
    entry's date range.

    AGGRESSIVE mode additionally allows APPROXIMATE counts (2..max) grounded
    in an enumerated list in the bullet/context/rewrite - 'multiple devices'
    may become '5 devices' when 5 items are enumerated nearby, and '3+' of a
    7-item list is fine.  The ABSOLUTE line holds in every mode: a number
    attached to a percentage, a currency amount, or any outcome metric with
    no source basis is always rejected, and a number with zero grounding
    (no enumeration anywhere) is always rejected.
    """
    allowed = set(_NUM_RE.findall(bullet)) | set(_NUM_RE.findall(context or ""))
    source = bullet + " " + (context or "")
    enum_ok = set()
    for m in _ENUM_RE.finditer(new):
        items = _enum_items(m.group(2))
        if items:
            enum_ok.add(m.group(1))
    grounding = None  # computed lazily, only in aggressive mode
    for m in _NUM_RE.finditer(new):
        n = m.group(0)
        if n in allowed or n in enum_ok:
            continue
        seg = new[max(0, m.start() - 2):m.end() + 10]
        if _DURATION_RE.search(seg):        # '4-week internship' etc.
            continue
        if aggressive:
            # ABSOLUTE fabrication line - %, currency, or any number glued
            # to an outcome claim is rejected even in aggressive mode.
            if ("%" in seg or re.search(r"[$\u20b9\u20ac\u00a3]|rs\.?", seg, re.I)
                    or re.search(r"\b(improv\w*|increas\w*|reduc\w*|sav\w*|"
                                 r"boost\w*|grow\w*)\b.{0,15}$", seg, re.I)):
                return True
            if grounding is None:
                grounding = _approx_counts_grounding(new, source)
            if grounding and 2 <= int(float(n)) <= max(grounding):
                continue                    # grounded approximation
            return True                     # zero grounding = pure invention
        return True                          # strict: strict rules apply
    return False                             #


def rewrite_bullet(bullet: str, context: str = "", aggressive: bool = False):
    """Return a stronger version of one resume bullet, or None on failure."""
    prompt = (
        "Rewrite this resume bullet point to be professional, active-voice, and "
        "impact-driven. Start with a strong, accurate action verb, keep it under "
        "30 words. Rules:\n"
        "- QUANTIFY FROM SOURCE: if the bullet or the Context contains any "
        "quantifiable detail (ratings, counts, durations, specs), work it in - "
        "counting items the bullet itself lists is allowed ('Studied 6 major "
        "substation components: CTs, CVTs, breakers...').\n"
        "- NEVER invent numbers, percentages, or outcomes that are not present in "
        "the bullet or Context and not directly countable from them. If nothing "
        "is quantifiable, strengthen specificity instead (what exactly, in what "
        "context, toward what purpose) - never a vague noun list.\n"
        "- STRONG VERBS: start with a verb implying action with judgment "
        "(inspected, evaluated, assessed, investigated, documented, analyzed, "
        "diagnosed, audited, tested). NEVER start with passive openers like "
        "'Observed', 'Gained exposure to', 'Acquired an understanding of', "
        "'Contributed to understanding', 'Learned about', 'Was involved in', "
        "'Worked on' - even when quantified.\n"
        "Reply with ONLY the rewritten bullet.\n\n"
        + ("Context: %s\n" % context if context else "")
        + "Bullet: %s" % bullet
    )
    out = _ask(prompt)
    if not out:
        return None
    fixed = _fix_enum_counts(out.strip().strip('"'))
    if _has_fabricated_number(fixed, bullet, context, aggressive=aggressive):
        # Unsafe rewrite: one strict retry (no new numbers) before keeping
        # the original - a plain fallback would preserve a weak opener.
        retry = _ask(
            "You are an expert resume writer. Rewrite this resume bullet to be "
            "professional and active-voice. STRICT: do NOT introduce ANY number "
            "that is not already in the bullet or Context - no counts, no "
            "durations. Strengthen the wording only.\n\n"
            + ("Context: %s\n" % context if context else "")
            + "Bullet: %s" % bullet)
        if retry:
            r2 = _fix_enum_counts(retry.strip().strip('"'))
            if not _has_fabricated_number(r2, bullet, context,
                                          aggressive=aggressive):
                return r2
        return None  # keep the original: it can only be accurate
    return fixed


def rewrite_bullets(bullets: list, context: str = "", used_verbs=None,
                    aggressive: bool = False):
    """Rewrite many bullets; returns list aligned with input (None per failure).

    used_verbs: opening verbs already used by OTHER entries of the same resume,
    so verb variation is enforced document-wide, not just within one call.
    aggressive: opt-in relaxed quantification - approximate counts grounded
    in enumerated lists are allowed; pure invention is still rejected.
    """
    if not bullets:
        return []
    verb_line = ""
    if used_verbs:
        if isinstance(used_verbs, dict):
            verb_line = (
                "Opening verbs already used elsewhere in this resume: %s. A verb "
                "used TWICE already is BANNED - do not start any bullet with it. "
                "A verb used once may appear at most once more. Prefer strong "
                "verbs not listed at all.\n"
                % ", ".join("%s (x%d)" % (v, c)
                            for v, c in sorted(used_verbs.items())))
        else:  # legacy set
            verb_line = (
                "Opening verbs already used elsewhere in this resume - do NOT start "
                "any bullet with these (one repeat at most): %s\n"
                % ", ".join(sorted(used_verbs)))
    rules = (
        "You are an expert resume writer. Rewrite EACH numbered resume bullet to "
        "be professional, active-voice, and impact-driven. Rules:\n"
        "1. QUANTIFY FROM SOURCE: look for ANY quantifiable detail already present "
        "in the bullet or the Context - voltage/power ratings, equipment or "
        "component counts, project/internship duration, number of systems, teams "
        "or people, frequency, scale of operation, stated technical specs - and "
        "work it into the bullet. Even observational/exposure-based work can be "
        "scaled: 'Studied 6 major substation components (CTs, CVTs, circuit "
        "breakers...) at a 400/220 kV facility' beats a bare noun list. Counting "
        "items the bullet itself lists, or citing specs stated in the Context, is "
        "allowed and encouraged - but count EXACTLY: if you enumerate items, the "
        "number must match the actual count (list 7 items -> say 7, or '7+'). "
        "When mentioning a duration, phrase it naturally ('during a 1-month "
        "internship') - never paste a raw date range into the sentence.\n"
        "2. NEVER FABRICATE: do not invent numbers, percentages, or outcomes that "
        "are not in the bullet or Context and are not directly countable from "
        "them (never add 'improved efficiency by 20%', 'saved 10 hours'). Never "
        "attach a number to a habit or generic activity that has no stated "
        "count ('reading tech blogs' must NOT become '3+ technical blogs "
        "weekly'). If a bullet has no quantifiable detail and none exists in "
        "the Context, strengthen SPECIFICITY and COMPLETENESS instead: state "
        "exactly what was "
        "done or observed, in what context, and toward what purpose - a "
        "complete statement, never a vague list of nouns. PRESERVE every number "
        "already present in the original bullet (ratings, counts, percentages) "
        "unless it is factually wrong in the Context - do not drop or round "
        "stated figures.\n"
        "3. STRONG VERBS ONLY: the opening verb must imply ACTION WITH JUDGMENT - "
        "the person DID something, not just watched. NEVER start a bullet with "
        "these weak/passive openers, even with a number attached: 'Observed', "
        "'Gained exposure to' / 'Gained practical exposure', 'Acquired an "
        "understanding of' / 'Acquired comprehensive knowledge of', 'Contributed "
        "to understanding', 'Learned about', 'Was involved in', 'Was responsible "
        "for', 'Worked on', 'Assisted with', 'Helped with'. For "
        "observational/exposure work use verbs that show engagement: inspected, "
        "evaluated, assessed, investigated, documented, analyzed, diagnosed, "
        "audited, examined, tested. Stay truthful - an intern who watched relay "
        "panels 'inspected' or 'audited' them, they did not 'design' or 'lead' "
        "them.\n"
        "4. VARY VERBS: within those strong verbs, do not start more than TWO "
        "bullets with the same opening verb. 'Analyzed', 'Examined' and "
        "'Inspected' are tempting defaults - spread across the whole strong bank "
        "so 8 bullets get 8 different openers.\n"
        "5. Keep each rewrite under 30 words and faithful to the original facts.\n"
        'Return ONLY a JSON object: {"rewrites": {"1": "...", "2": "..."}}\n\n'
    )
    if aggressive:
        rules += (
            "6. AGGRESSIVE QUANTIFICATION MODE (user explicitly opted in): you may "
            "convert vague scope words ('multiple', 'several', 'various', "
            "'various types of') into a specific count ONLY when that count is "
            "directly inferable from an enumerated list in the bullet or Context "
            "('studied multiple protection devices' + 5 devices listed -> '5 "
            "protection devices'; or '3+' of a 7-item list). You may also frame "
            "durations/scale slightly more freely ('a multi-week internship', "
            "'close to a month'). STILL ABSOLUTELY FORBIDDEN even in this mode: "
            "percentages, money amounts, or outcome metrics with no basis in the "
            "source ('improved efficiency by 20%'), and ANY number with zero "
            "grounding - if no enumeration or figure exists anywhere, do not "
            "invent one. These are educated estimates: never present them as "
            "verified facts.\n"
        )

    def _build(bs, strict=False, extra=""):
        return (rules
                + ("STRICT: do NOT introduce ANY number that is not already in "
                   "the bullet or Context - no counts, no durations. Strengthen "
                   "the wording only.\n" if strict else "")
                + extra
                + ("Context (may contain quantifiable details worth surfacing): "
                   "%s\n" % context if context else "")
                + verb_line
                + "\n".join("%d. %s" % (i + 1, b) for i, b in enumerate(bs)))

    def _opener(s):
        w = s.split(None, 1)
        return w[0].strip(",.:-;").lower() if w else ""

    data = _ask_json(_build(bullets))
    if not isinstance(data, dict):
        return [None] * len(bullets)
    mapping = data.get("rewrites", {})
    out, rejected = [], []
    for i, b in enumerate(bullets):
        r = mapping.get(str(i + 1)) or mapping.get(i + 1)
        if r:
            r = str(r).strip()
            r = _fix_enum_counts(r)
            if _has_fabricated_number(r, b, context, aggressive=aggressive):
                r = None  # unsafe rewrite - retried strictly below
        out.append(r or None)
        if r is None:
            rejected.append(i)
    # A rejected rewrite would otherwise fall back to the ORIGINAL bullet,
    # which keeps weak/passive openers in the resume.  Give those bullets one
    # bounded strict retry (no new numbers) before keeping the original.
    if rejected:
        data2 = _ask_json(_build([bullets[i] for i in rejected], strict=True))
        if isinstance(data2, dict):
            m2 = data2.get("rewrites", {})
            for k, i in enumerate(rejected):
                r = m2.get(str(k + 1)) or m2.get(k + 1)
                if r:
                    r = str(r).strip()
                    r = _fix_enum_counts(r)
                    if not _has_fabricated_number(r, bullets[i], context,
                                                  aggressive=aggressive):
                        out[i] = r
    # Enforce the two-max opener cap deterministically: the count signal
    # constrains verbs used by EARLIER entries, but a single batch can still
    # return 3+ bullets opening with the same verb.  Re-ask for the excess.
    opener_counts = {}
    for r in out:
        if r:
            v = _opener(r)
            opener_counts[v] = opener_counts.get(v, 0) + 1
    over = [v for v, c in opener_counts.items() if c > 2]
    if over:
        seen = {}
        retry_idx = []
        for i, r in enumerate(out):
            if not r:
                continue
            v = _opener(r)
            if v in over:
                seen[v] = seen.get(v, 0) + 1
                if seen[v] > 2:  # keep the first two occurrences
                    retry_idx.append(i)
        if retry_idx:
            extra = ("BANNED opening verbs (already used twice in this resume): "
                     "%s\n" % ", ".join(over))
            data3 = _ask_json(_build([bullets[i] for i in retry_idx],
                                     strict=True, extra=extra))
            if isinstance(data3, dict):
                m3 = data3.get("rewrites", {})
                for k, i in enumerate(retry_idx):
                    r = m3.get(str(k + 1)) or m3.get(k + 1)
                    if r:
                        r = str(r).strip()
                        r = _fix_enum_counts(r)
                        if (not _has_fabricated_number(r, bullets[i], context,
                                                       aggressive=aggressive)
                                and _opener(r) not in over):
                            out[i] = r
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
    # Degenerate structures (empty sections or empty name) are rejected here
    # so a half-baked Gemini answer can never render a placeholder resume -
    # the caller falls back to the rule-based structured parse instead.
    if (isinstance(data, dict) and isinstance(data.get("sections"), list)
            and data["sections"] and (data.get("name") or "").strip()):
        data.setdefault("headline", "")
        data.setdefault("contacts", [])
        return data
    return None
