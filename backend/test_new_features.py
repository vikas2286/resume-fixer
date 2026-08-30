"""Verification for: template fixes (spacing/education/skills/CGPA-order),
fix-mode assessment (minor vs full), and the Content Quality score."""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parser as rp
import scoring
import template_engine as te
from fastapi.testclient import TestClient
import main as app_module

HARSH = r"C:\Users\HP\Downloads\Harsh Arya Resume##.pdf"
MESSY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "messy_resume.pdf")
VIKAS = r"C:\Users\HP\Downloads\VIKAS_1by23is249_Bmsit.pdf"

fails = 0
def check(name, ok, extra=""):
    global fails
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, extra))
    fails += 0 if ok else 1


# ---------------------------------------------------------------- Task A
print("\n===== A1/A2/A4: Harsh render (spacing / education blocks / skills) =====")
p = rp.parse_pdf(HARSH)
st = p["structured"]
html = te.render_html(st, "classic")

# skills bold labels
n_labels = html.count('<span class="label">')
check("skills: >=5 bolded category labels", n_labels >= 5,
      "(found %d)" % n_labels)
check("skills label example", "Languages:</span>" in html)
check("skills items render (no Jinja attr leak)",
      "built-in method" not in html
      and "JavaScript (ES6+)" in html)

# education block layout: meta as its own div for bullet-less entries
# (match by canonical key - the source header text may be misspelled)
edu_sec = next(s for s in st["sections"] if s["type"] == "entries"
               and s.get("key") == "education")
e2 = edu_sec["entries"][1]
check("education entry2 has meta + no bullets",
      bool(e2.get("meta")) and not e2.get("bullets"))
check("education entry2 meta rendered as separate <div>",
      ('<div class="entry-meta">B.D. Inter College' in html))
check("no 'Board &mdash;' concatenation", "Board &mdash;" not in html)

# section spacing present in CSS of generated html
check("section spacing top margin on h2", "margin: 16px 0 6px 0" in html)

pdf = te.generate_pdf(st, "classic")
open("_verify_classic.pdf", "wb").write(pdf)
import fitz
doc = fitz.open("_verify_classic.pdf")
text = doc[0].get_text()
check("still single page after spacing change", doc.page_count == 1,
      "(pages=%d)" % doc.page_count)
i_btech = text.find("Bachelor of Technology")
i_ssc = text.find("Senior Secondary (XII)")
check("both education entries present", i_btech > -1 and i_ssc > -1)

# ---------------------------------------------------------------- Task A3
print("\n===== A3: conditional Education placement =====")
base_secs = json.loads(json.dumps(st["sections"]))

def order_of(html_str, titles):
    import re as _re
    heads = _re.findall(r"<h2>(.*?)</h2>", html_str)
    tl = {t.lower() for t in titles}
    return [h for h in heads if h.lower() in tl]

titles = ["SUMMARY", "EDUCATION", "SKILLS", "PROJECTS"]

hi = json.loads(json.dumps(base_secs))
low = json.loads(json.dumps(base_secs))
pct_hi = json.loads(json.dumps(base_secs))
pct_lo = json.loads(json.dumps(base_secs))
for h, l, ph, pl in zip(hi, low, pct_hi, pct_lo):
    if h["type"] == "entries" and h.get("key") == "education":
        h["entries"][0]["meta"] = "CGPA: 9.0"
        l["entries"][0]["meta"] = "CGPA: 6.4"
        ph["entries"][0]["meta"] = "87%"
        pl["entries"][0]["meta"] = "83%"

# Normalize fixture labels to canonical names: placement is driven by the
# canonical KEY, and these assertions check ORDER, not source label fidelity.
_CANON = {"summary": "Summary", "education": "Education",
          "skills": "Skills", "projects": "Projects"}
for _sec in hi + low + pct_hi + pct_lo:
    _k = (_sec.get("key") or "").lower()
    if _k in _CANON:
        _sec["title"] = _CANON[_k]

html_hi = te.render_html({"name": "T", "sections": hi}, "classic")
html_low = te.render_html({"name": "T", "sections": low}, "classic")
o_hi = order_of(html_hi, titles)
o_low = order_of(html_low, titles)
print("  high-CGPA order:", o_hi)
print("  low-CGPA order :", o_low)
check("CGPA 9.0 (>=8.5) -> Education first", o_hi[0] == "Education")
check("CGPA 9.0 -> before Summary",
      o_hi.index("Education") < o_hi.index("Summary"))
check("low CGPA -> Education moved AFTER Projects (not promoted)",
      o_low == ["Summary", "Projects", "Skills", "Education"])
html_pct = te.render_html({"name": "T", "sections": pct_hi}, "classic")
check("percent 87% (>=85, no CGPA) also promotes Education",
      order_of(html_pct, titles)[0] == "Education")
html_pct2 = te.render_html({"name": "T", "sections": pct_lo}, "classic")
check("percent 83% (<85) stays after Projects",
      order_of(html_pct2, titles) == ["Summary", "Projects", "Skills",
                                      "Education"])

# ---------------------------------------------------------------- Task B
print("\n===== B: fix-mode assessment =====")
c = TestClient(app_module.app)
for label, path, expect_major in [("messy resume", MESSY, True),
                                  ("Vikas Gupta LaTeX", VIKAS, False)]:
    with open(path, "rb") as f:
        up = c.post("/upload", files={"file": ("r.pdf", f)}).json()
    sc = up["scores"]
    print("  %-20s ats=%s visual=%s overall=%s content=%s flags=%d"
          % (label, sc["ats"]["score"], sc["visual"]["score"],
             sc["overall"], sc["content"]["score"],
             len(up["fix_assessment"]["minor_suggestions"])))
    check("%s needs_major_fix=%s" % (label, expect_major),
          up["needs_major_fix"] is expect_major,
          "| mode=%s | %s" % (up["fix_mode"],
                              up["fix_assessment"]["message"]))
    sid = up["session_id"]
    g = c.get("/score/%s" % sid).json()
    check("%s /score exposes needs_major_fix" % label,
          g.get("needs_major_fix") is expect_major)

# ---------------------------------------------------------------- Task C
print("\n===== C: content quality score shape =====")
cq = scoring.content_quality_score(p)
print("  Harsh content=%s dims=%s"
      % (cq["score"], {d["dimension"]: d["earned"] for d in cq["dimensions"]}))
check("content score in 0-100", 0 <= cq["score"] <= 100)
check("5 dimensions present",
      len(cq["dimensions"]) == 5 and len(cq["checks"]) == 5)
full = scoring.score_resume(p)
check("score_resume returns content category", "content" in full)
check("overall NOT blended with content",
      full["overall"] == round(full["ats"]["score"] * 0.6
                               + full["visual"]["score"] * 0.4))
thin = {"structured": {"sections": [
    {"title": "Projects", "type": "entries", "entries": [
        {"title": "X", "bullets": ["responsible for website"]}]}]}}
cq_thin = scoring.content_quality_score(thin)
check("thin/generic resume scores low content", cq_thin["score"] <= 30,
      "(score=%d)" % cq_thin["score"])

print("\nNEW-FEATURES %s" % ("ALL PASSED" if fails == 0 else "%d FAILED" % fails))
sys.exit(1 if fails else 0)


