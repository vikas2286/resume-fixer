"""C.8: summary bolding dual-path proof.

Path A: Gemini picks 3-5 noun phrases (real API when key present).
Path B: no key -> deterministic metric-only bolding fallback.
Prints the actual bolded HTML for both and asserts sanity invariants.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import html as _htmlmod
import re as _re

import llm_service as llm
import template_engine as te

SUMMARY = ("Energetic Backend Developer with 2 years of experience building "
           "scalable REST APIs with Django and PostgreSQL. Improved "
           "throughput by 40% and cut p99 latency by 35% across "
           "microservices serving 1M+ requests per day. Passionate about "
           "cloud infrastructure, clean architecture and mentoring junior "
           "engineers.")

fails = []


def check(name, cond, detail=""):
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        fails.append(name)


def strong_phrases(html):
    return _re.findall(r"<strong>(.*?)</strong>", html)


# ---- Path B: no key -------------------------------------------------------
# NB: _get_model() caches its attempt in _tried; snapshot & restore so the
# no-key simulation here can't poison the real-key path below.
_key_backup, _tried_backup, _model_backup = (llm.GEMINI_API_KEY, llm._tried,
                                             llm._model)
llm.GEMINI_API_KEY = ""
llm._tried, llm._model = True, None
html_b = te._bold_summary(SUMMARY)
llm.GEMINI_API_KEY, llm._tried, llm._model = (_key_backup, _tried_backup,
                                              _model_backup)
print("PATH B (rules) -> %s" % html_b)
tags_b = strong_phrases(str(html_b))
check("B: metric-only bolding", bool(tags_b)
      and all(_re.match(r"^[\d.,]+[%+x\u00d7]?$", t) for t in tags_b),
      "bolded=%s" % tags_b)

# ---- Path A: Gemini (real call when key configured) -----------------------
if llm.gemini_available():
    print("...calling Gemini (%s) for summary phrase selection..."
          % llm.MODEL_NAME)
    html_a = te._bold_summary(SUMMARY)
    print("PATH A (gemini) -> %s" % html_a)
    tags_a = strong_phrases(str(html_a))
    check("A: 1-5 phrases bolded", 1 <= len(tags_a) <= 5,
          "bolded=%s" % tags_a)
    plain = _htmlmod.unescape(
        _re.sub(r"\s+", " ", _re.sub(r"</?strong>", "", str(html_a)))).strip()
    plain_src = _re.sub(r"\s+", " ", SUMMARY).strip()
    check("A: bolding only wraps existing text (no injection)",
          plain == plain_src, "")
    check("A: path emits phrase-level bold (not just metrics)",
          any(not _re.match(r"^[\d.,]+[%+x\u00d7]?$", t) for t in tags_a),
          "")
else:
    print("PATH A: no key configured -> skipped (Path B verified above)")

# ---- render pipeline integration (paragraph section) ----------------------
st = {"sections": [{"title": "Summary", "type": "paragraph",
                    "text": SUMMARY}]}
te._prep_entries(st["sections"])
html_r = st["sections"][0]["text_html"]
check("pipeline: paragraph sections go through dual-path bolding",
      "<strong>" in str(html_r), str(html_r)[:80])

print("\n== C.8: %s ==" % ("GREEN - 0 failures" if not fails
                           else "RED: %s" % fails))
sys.exit(1 if fails else 0)
