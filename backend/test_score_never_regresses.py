"""Score-regression gate: "Fix My Resume" must NEVER make a resume score worse.

Born from the Gopal Jha regression (ATS 92 -> 81 in the wild): the parser's
contact_in_header_footer heuristic flagged the page-1 letterhead as a "header"
on every multi-page rebuild, so any resume whose fixed PDF spilled to 2 pages
lost ATS points for a perfectly normal contact block.

Two layers of protection:

1. GENERAL INVARIANT (every resume, forever): for every *-_resume.pdf fixture
   in this directory - plus any fixture added later matching that pattern -
   the fixed PDF's OVERALL score must be >= the original's. Add a new fixture
   file and it is automatically covered.

2. GOPAL-SPECIFIC: the exact reported failure mode - ATS category dropping
   and contact_in_body flipping to fail after the fix - is asserted directly.
"""
import glob
import json
import os

import fitz

import llm_service
import parser as resume_parser
import scoring
import template_engine

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_regress_fixed.pdf")

fails = 0


def check(name, ok, detail=""):
    global fails
    print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                         "  %s" % detail if detail and not ok else ""))
    if not ok:
        fails += 1


# Deterministic + offline: no Gemini summary-bolding calls (network/quota make
# scores flaky). Pattern from test_c8_summary.py.
_key_backup = llm_service.GEMINI_API_KEY
llm_service.GEMINI_API_KEY = ""

try:
    # Every resume fixture - future ones included - inherits the invariant.
    fixtures = sorted(glob.glob(os.path.join(HERE, "*_resume.pdf")))
    if os.path.exists(os.path.join(HERE, "stress_fresher.pdf")):
        fixtures.append(os.path.join(HERE, "stress_fresher.pdf"))
    check("fixture count >= 8 (Gopal is the 8th)", len(fixtures) >= 8,
          "found %d: %s" % (len(fixtures),
                            [os.path.basename(f) for f in fixtures]))

    regressions = []
    for path in fixtures:
        name = os.path.basename(path)
        parsed = resume_parser.parse_pdf(path)
        before = scoring.score_resume(parsed)
        template_engine.generate_pdf(
            parsed["structured"], "auto", out_path=OUT,
            max_pages=max(1, int(parsed.get("n_pages") or 1)))
        fixed = resume_parser.parse_pdf(OUT)
        after = scoring.score_resume(fixed)

        ok = after["overall"] >= before["overall"]
        detail = "overall %s -> %s (ats %s -> %s, visual %s -> %s)" % (
            before["overall"], after["overall"],
            before["ats"]["score"], after["ats"]["score"],
            before["visual"]["score"], after["visual"]["score"])
        check("INVARIANT after>=before: %s" % name, ok, detail)
        if not ok:
            regressions.append((name, detail))

    # ---- Gopal-specific: the exact reported failure mode -------------------
    gopal = os.path.join(HERE, "gopal_resume.pdf")
    check("gopal fixture present", os.path.exists(gopal))
    parsed = resume_parser.parse_pdf(gopal)
    before = scoring.score_resume(parsed)
    template_engine.generate_pdf(parsed["structured"], "auto", out_path=OUT,
                                 max_pages=max(1, int(parsed.get("n_pages") or 1)))
    fixed = resume_parser.parse_pdf(OUT)
    after = scoring.score_resume(fixed)

    check("gopal: ATS after >= ATS before",
          after["ats"]["score"] >= before["ats"]["score"],
          "%s -> %s" % (before["ats"]["score"], after["ats"]["score"]))
    contact_after = [c for c in after["ats"]["checks"]
                     if c["check"] == "contact_in_body"]
    check("gopal: contact_in_body passes after fix",
          bool(contact_after) and contact_after[0]["passed"],
          contact_after[0]["reason"] if contact_after else "check missing")
    check("gopal: fixed parse has no header/footer contact flag",
          not fixed.get("contact_in_header_footer", False))

    if regressions:
        print("\nSCORE REGRESSIONS:")
        for n, d in regressions:
            print("  %s: %s" % (n, d))
    print("\n%s" % ("ALL SCORE-INVARIANT CHECKS PASSED" if fails == 0
                    else "%d CHECK(S) FAILED" % fails))
finally:
    llm_service.GEMINI_API_KEY = _key_backup
    if os.path.exists(OUT):
        os.remove(OUT)

raise SystemExit(1 if fails else 0)