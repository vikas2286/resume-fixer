"""Data-integrity test: parse realistic_resume.pdf, render it back to PDF,
and assert the reported bugs are gone.

  1. no bullet text appears more than once in the output
  2. every project header (AgentFlow, ResumeRanker) survives as a heading
  3. education renders cleanly: no "· 1" glue, CGPA kept, date kept
  4. page count of output <= page count of original

Run: python backend/test_data_integrity.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz  # noqa: E402

import parser as resume_parser  # noqa: E402
import template_engine  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "realistic_resume.pdf")
OUT = os.path.join(BASE, "realistic_fixed.pdf")

FAILS = []


def check(name, cond, detail=""):
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        FAILS.append(name)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def all_bullets(structured):
    out = []
    for sec in structured.get("sections", []):
        if sec.get("type") == "entries":
            for e in sec.get("entries", []):
                out += e.get("bullets", [])
    return out


def find_entry(structured, title_prefix):
    for sec in structured.get("sections", []):
        if sec.get("type") == "entries":
            for e in sec.get("entries", []):
                if e.get("title", "").lower().startswith(title_prefix.lower()):
                    return e
    return None


def main():
    parsed = resume_parser.parse_file(SRC)
    st = parsed["structured"]

    # ---- structured-JSON level ------------------------------------------
    bullets = all_bullets(st)
    dupes = {b for b in bullets if bullets.count(b) > 1}
    check("no duplicate bullets in JSON", not dupes, str(dupes) if dupes else "")

    agentflow = find_entry(st, "AgentFlow")
    ranker = find_entry(st, "ResumeRanker")
    check("project 'AgentFlow' is its own entry",
          agentflow is not None and len(agentflow["bullets"]) >= 1,
          "(%d bullets)" % len(agentflow["bullets"]) if agentflow else "missing")
    check("project 'ResumeRanker' is its own entry",
          ranker is not None and len(ranker["bullets"]) >= 1,
          "(%d bullets)" % len(ranker["bullets"]) if ranker else "missing")
    af_bullets = set(agentflow["bullets"]) if agentflow else set()
    rk_bullets = set(ranker["bullets"]) if ranker else set()
    check("project bullets not merged across projects",
          not (af_bullets & rk_bullets))

    edu = find_entry(st, "B.Tech")
    check("education entry found with degree title", edu is not None)
    if edu:
        check("education has NO stray '· 1' glue",
              "\u00b7 1" not in edu["title"] and "\u00b7 1" not in edu["meta"],
              repr(edu["title"] + " | " + edu["meta"]))
        check("education keeps CGPA", "7.82" in edu["meta"], edu["meta"])
        check("education keeps full date range",
              "2023" in edu["date"] and "2027" in edu["date"], edu["date"])
        check("education date not duplicated inside title/meta",
              edu["date"] not in edu["title"] and edu["date"] not in edu["meta"])

    exp = find_entry(st, "Software Engineer, TechCorp")
    check("experience entry intact",
          exp is not None and len(exp["bullets"]) == 3)

    # ---- rendered PDF level ----------------------------------------------
    template_engine.generate_pdf(st, "classic", out_path=OUT)
    doc_out = fitz.open(OUT)
    text = norm(" ".join(p.get_text("text") for p in doc_out))
    out_pages = doc_out.page_count
    src_pages = fitz.open(SRC).page_count

    for b in set(bullets):
        n = text.count(norm(b))
        check("bullet appears exactly once in PDF (%s...)" % norm(b)[:40],
              n == 1, "count=%d" % n)
    check("'AgentFlow' heading present in PDF", "AgentFlow" in text)
    check("'ResumeRanker' heading present in PDF", "ResumeRanker" in text)
    check("no '· 1' glue in PDF", "\u00b7 1" not in text)
    check("CGPA preserved in PDF", "7.82" in text)
    check("education date preserved in PDF", "Sep 2023" in text and "2027" in text)
    check("page count did not grow (out<=src)",
          out_pages <= src_pages, "out=%d src=%d" % (out_pages, src_pages))

    print("\n%d checks failed" % len(FAILS)) if FAILS \
        else print("\nALL INTEGRITY CHECKS PASSED")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
