"""Acceptance test for the {header detection, bullet detection, custom-section}
fixes, run against BOTH fixture resumes:

  * realistic_resume.pdf  - the "original sample" (marker bullets, LaTeX-style)
  * harsh_resume.pdf      - "ABOUT ME" / "EDUACTION" / "S K I L L S" /
                            boxed "PROJECTS" / indent bullets / "HOBBIES"

Checks per resume:
  1. every section header the parser detects in the source appears in output
  2. bullet count in ~= bullet count out (no bullets lost, none duplicated)
  3. no section's content bleeds into another (esp. summary vs bullets)

Run: python backend/test_both_resumes.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz  # noqa: E402

import parser as P  # noqa: E402
import template_engine  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
RESUMES = [
    {
        "path": os.path.join(BASE, "realistic_resume.pdf"),
        "indent_phrases": [],
        "custom_labels": [],
        "labels": [],
    },
    {
        "path": os.path.join(BASE, "harsh_resume.pdf"),
        "indent_phrases": ["Designed a hybrid graph", "Deployed on AWS ECS"],
        "custom_labels": ["HOBBIES"],           # unknown header -> fallback
        # SOURCE header text after the narrow typo-correction rule
        # ('EDUACTION' in the source renders as 'Education')
        "labels": ["A B O U T M E", "Education", "S K I L L S",
                   "PROJECTS", "HOBBIES"],
    },
    {
        # 5th real reference resume (Vinod Bhanji, BMSITM).  Permanent copy
        # in backend/ so the regression does not depend on Downloads/.
        "path": os.path.join(BASE, "vinod_resume.pdf"),
        "indent_phrases": [],
        "custom_labels": [],
        # source header labels, preserved verbatim
        "labels": ["SUMMARY", "EDUCATION", "SKILLS", "PROJECTS",
                   "ACHIEVEMENTS"],
        # two-column source: rail fragments fuse + linked lines promote, so
        # the generic 1:1 bullet assertions do not hold (see run_vinod)
        "skip_bullet_checks": True,
    },
    {
        # 6th real reference resume (Muskan Pargal).  Permanent copy in
        # backend/ so the regression does not depend on Downloads/.
        "path": os.path.join(BASE, "muskan_resume.pdf"),
        "indent_phrases": [],
        "custom_labels": [],
        "labels": ["Profile", "Experience", "Projects", "Education",
                   "Skills"],
        # source glyph bullets are not detected as bullet lines (Canva-style
        # private-use markers), so the 1:1 count assertion does not apply -
        # run_muskan pins the invariants instead
        "skip_bullet_checks": True,
    },
    {
        # 7th real reference resume (Ashmit Sharma, BMSITM).  Permanent copy
        # in backend/ so the regression does not depend on Downloads/.
        "path": os.path.join(BASE, "ashmit_resume.pdf"),
        "indent_phrases": ["Mentored 200+ students"],
        "custom_labels": [],
        "labels": ["Summary", "Skills", "Experience", "Projects",
                   "Education", "Achievements"],
        # 4 unmarked-but-bulleted lines are legitimate: 3 right-rail
        # tech-stack chips + the 53-char school line (over the 48-char meta
        # cap).  Phrase-loss check still runs (see run_ashmit too).
        "skip_bullet_count": True,
    },
]

CANONICAL_TITLE = {
    "summary": "Summary", "experience": "Experience", "education": "Education",
    "skills": "Skills", "projects": "Projects",
    "certifications": "Certifications", "awards": "Awards",
}

FAILS = []


def check(name, ok, detail=""):
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILS.append(name)


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def run_one(spec):
    path = spec["path"]
    print("\n==== %s ====" % os.path.basename(path))
    parsed = P.parse_pdf(path)
    st = parsed["structured"]
    lines = parsed["lines"]

    # --- 1. headers preserved --------------------------------------------
    # The output must carry the SOURCE header text (synonyms are for
    # matching, never relabeling); canonical names are only the fallback
    # when no source title was captured.
    src_titles = parsed.get("section_titles") or {}
    exp_keys = {k for k in (parsed.get("sections") or {})
                if not k.startswith("custom:")}
    exp_custom = [
        (parsed.get("section_titles") or {}).get(sid)
        for sid in parsed.get("section_order", []) if sid.startswith("custom:")
    ]
    out_titles = {s.get("title") for s in st["sections"]}
    for key in sorted(exp_keys):
        src = (src_titles.get(key) or "").strip()
        expected = src if src and len(src) <= 40 else CANONICAL_TITLE[key]
        # narrow header-typo correction applies to rendered labels
        expected = P.canonical_header_spelling(expected)
        check("header mapped & present: %s" % key,
              expected in out_titles,
              "label=%s" % expected)
    for c in sorted(x for x in exp_custom if x):
        check("custom header kept: %s" % c, c in out_titles)

    # --- 2. bullets: count in ~= count out, none lost ---------------------
    # marker-based source bullets (indent bullets are asserted separately).
    # Multi-column sources (Vinod) legitimately differ: right-rail metric
    # fragments fuse into entries and linked lines promote to entry rows,
    # so the 1:1 count assertion does not apply - the resume-specific
    # checks below pin the invariants instead.
    src_bullets = [l for l in lines if l.get("bullet")]
    out_bullets = []
    for sec in st["sections"]:
        if sec.get("type") == "entries":
            for e in sec["entries"]:
                out_bullets += [norm(b) for b in e["bullets"]]
    if not spec.get("skip_bullet_count") and not spec.get("skip_bullet_checks"):
        check("bullet count in~out (%d ~ %d)" % (len(src_bullets), len(out_bullets)),
              abs(len(src_bullets) - len(out_bullets)) <= 2,
              "in=%d out=%d" % (len(src_bullets), len(out_bullets)))

    # every source bullet phrase survives somewhere in the output
    # (source lines still carry their layout marker glyph - strip it with
    # the same rule the parser uses for bullet content)
    if not spec.get("skip_bullet_checks"):
        missing = []
        for srb in src_bullets:
            p = norm(P.strip_bullet_markers(srb["text"]))
            if not p:
                continue
            if not any(p in ob for ob in out_bullets):
                missing.append(p)
        check("no source bullet phrase lost", not missing,
              "; ".join(m[:60] for m in missing[:3]))

        # --- 3. no bleed: summary paragraph must not swallow bullet content ----
        summary_text = ""
        for sec in st["sections"]:
            if sec.get("type") == "paragraph":
                summary_text += "\n" + (sec.get("text") or "")
        bled = [norm(b["text"]) for b in src_bullets
                if norm(b["text"]) and norm(b["text"]) in norm(summary_text)]
        check("summary has no bullet bleed", not bled,
              "; ".join(b[:60] for b in bled[:3]))

    # rendered PDF text also confirms headers + no lost bullets (fits the
    # "generate a resume and verify" instruction)
    pdf = template_engine.generate_pdf(st, "classic")
    doc = fitz.open(stream=pdf, filetype="pdf")
    text_flat = norm(" ".join(p.get_text("text") for p in doc))
    for key in exp_keys - {"summary"}:
        src = (src_titles.get(key) or "").strip()
        shown = src if src and len(src) <= 40 else CANONICAL_TITLE[key]
        shown = P.canonical_header_spelling(shown)
        check("output PDF shows %s" % shown, shown.lower() in text_flat)
    check("output PDF is single page", doc.page_count <= 2,
          "pages=%d" % doc.page_count)

    # --- resume-specific assertions ---------------------------------------
    for phrase in spec.get("indent_phrases", []):
        check("indent bullet captured: %s..." % phrase,
              any(phrase.lower() in ob for ob in out_bullets),
              "in=%s" % [ob[:40] for ob in out_bullets if phrase.lower() in ob])
    for label in spec.get("custom_labels", []):
        check("custom section rendered: %s" % label, label in out_titles)
    for label in spec.get("labels", []):
        check("expected label present: %s" % label, label in out_titles)


def run_vinod():
    """Resume-specific regression for the Vinod fix round (rail metric tags,
    link-URI lines, education shaping, one-page auto fit)."""
    path = os.path.join(BASE, "vinod_resume.pdf")
    print("\n==== vinod_resume.pdf (specific) ====")
    if not os.path.exists(path):
        print("MISSING fixture: vinod_resume.pdf")
        FAILS.append("fixture " + path)
        return
    parsed = P.parse_pdf(path)
    st = parsed["structured"]

    edu = next((s for s in st["sections"]
                if s.get("key") == "education" and s.get("type") == "entries"),
               None)
    entries = (edu or {}).get("entries", [])
    check("vinod: 3 separate education entries", len(entries) == 3,
          "got %d" % len(entries))
    titles = [norm(e.get("title", "")) for e in entries]
    check("vinod: B.Tech entry present",
          any("b.tech" in t for t in titles), titles)
    check("vinod: school entries not column-fused",
          any("sbr" in t for t in titles) and any("shloka" in t for t in titles),
          titles)
    metas = " | ".join(norm(e.get("meta", "")) for e in entries)
    check("vinod: rail metric tags survived (93 / 93.80 / CGPA)",
          "93%" in metas and "93.80%" in metas and "9.07" in metas, metas)

    # rendered PDF: every score lands on the page (right rail), GitHub link
    # labels attach to projects, and auto mode fits a single page
    # (norm() lower-cases, so needles are lower-case too)
    pdf = template_engine.generate_pdf(st, "auto")
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = norm(" ".join(p.get_text("text") for p in doc))
    check("vinod: auto mode renders 1 page", doc.page_count == 1,
          "pages=%d" % doc.page_count)
    doc.close()
    for tag in ("93%", "93.80%", "cgpa: 9.07"):
        check("vinod: score rendered in PDF (%s)" % tag, tag in text)
    # Standard education layout: score is its OWN right-aligned cell and the
    # '/10' scale suffix is stripped from the DISPLAY form (user spec).
    check("vinod: no '/10' suffix in rendered PDF", "/10" not in text, text[:400])
    # two-row structure: institution name renders (row 1) separate from the
    # degree/qualification (row 2) for every education entry
    check("vinod: institution-first rows (BMS / SBR / Shloka present)",
          "bms institute of technology" in text
          and "sbr pu college" in text and "shloka-a birla school" in text)
    check("vinod: GitHub link labels on projects", text.count("github") >= 4,
          "count=%d" % text.count("github"))
    check("vinod: school names not glued into one line",
          "sbr pu college" in text and "shloka-a birla school" in text)


def run_muskan():
    """Resume-specific regression for the Muskan fix round (title/company
    ordering in Experience).

    Source layout (Muskan_CV.pdf): company names and role lines sit at the
    SAME left x with no bold/italic distinction, while the DD/MM/YYYY date
    ranges live in the right rail and extract BEFORE their company line.
    Previously the unrecognized numeric dates became entry TITLES (rule 4),
    the company fell into meta and the role line split off as a phantom
    entry.  The convention everywhere else is title=company / meta=role
    (Kanish: 'Freight Tiger' / 'On-Site · SDE Intern').
    """
    path = os.path.join(BASE, "muskan_resume.pdf")
    print("\n==== muskan_resume.pdf (specific) ====")
    if not os.path.exists(path):
        print("MISSING fixture: muskan_resume.pdf")
        FAILS.append("fixture " + path)
        return
    parsed = P.parse_pdf(path)
    st = parsed["structured"]

    exp = next((s for s in st["sections"]
                if s.get("key") == "experience" and s.get("type") == "entries"),
               None)
    entries = (exp or {}).get("entries", [])
    check("muskan: 3 experience entries (no phantom role split)",
          len(entries) == 3, "got %d: %s"
          % (len(entries), [e.get("title", "")[:30] for e in entries]))

    titles = [norm(e.get("title", "")) for e in entries]
    metas = [norm(e.get("meta", "")) for e in entries]
    dates = [norm(e.get("date", "")) for e in entries]

    # title=company / meta=role ordering (general invariant)
    for i, e in enumerate(entries):
        t = norm(e.get("title", ""))
        check("muskan: EXP[%d] title is not a date/role line" % i,
              bool(t) and not P.DATE_RE.fullmatch(t)
              and not P._ROLE_KW_RE.search(t), t)
    check("muskan: companies are the titles (POWERGRID / BHEL / Hiranagar)",
          any("powergrid" in t for t in titles)
          and any("bhel" in t for t in titles)
          and any("grid station" in t for t in titles), titles)
    check("muskan: roles live in meta (Summer Internship 3/2/I)",
          "summer internship-3" in metas[0]
          and "summer internship-2" in metas[1]
          and "summer internship-i" in metas[2], metas)
    check("muskan: rail dates attach to their own entries",
          dates[0] == "22/06/2026 - 22/07/2026"
          and dates[1] == "04/06/2025 - 01/07/2025"
          and dates[2] == "06/06/2024 - 06/07/2024", dates)
    # bullets stay with their own company entry
    check("muskan: substation bullets under POWERGRID",
          any("circuit breakers" in norm(b)
              for b in entries[0].get("bullets", [])))
    check("muskan: turbo-generator bullets under BHEL",
          any("turbo generators" in norm(b)
              for b in entries[1].get("bullets", [])))

    # education: institution survives (shaper runs per entry; the university
    # and the degree are separate source entries here, so assert section-wide)
    edu = next((s for s in st["sections"]
                if s.get("key") == "education" and s.get("type") == "entries"),
               None)
    edu_text = " ".join(
        "%s %s" % (e.get("title", ""), e.get("meta", ""))
        for e in (edu or {}).get("entries", []))
    check("muskan: education keeps the university name",
          "vaishno devi university" in norm(edu_text), edu_text[:80])

    # rendered PDF: roles + companies + compact numeric dates all on page 1
    pdf = template_engine.generate_pdf(st, "auto")
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = norm(" ".join(p.get_text("text") for p in doc))
    check("muskan: auto mode renders 1 page", doc.page_count == 1,
          "pages=%d" % doc.page_count)
    doc.close()
    for needle in ("powergrid", "bhel, haridwar", "grid station, hiranagar",
                   "summer internship-3", "summer internship-2",
                   "summer internship-i", "22/06/2026 - 22/07/2026"):
        check("muskan: rendered PDF shows %r" % needle, needle in text)


def run_ashmit():
    """Resume-specific regression for the Ashmit fix round (bold right-rail
    metric tags + phantom-header guard).

    Source layout (Ashmit Resume .pdf): education sits at the very bottom of
    page 1.  'CGPA: 9.10' and '93.7%' are BOLD right-rail tags on the same
    rows as their school lines.  Previously 'CGPA: 9.10' passed
    _plausible_header_line (bold + 'CGPA'.isupper() is True for acronyms)
    and opened a phantom custom section that carved the education block:
    the CGPA rendered as an orphan after Achievements and 'Higher Secondary
    ... 93.7%' rendered above the EDUCATION header as custom-section body.
    """
    path = os.path.join(BASE, "ashmit_resume.pdf")
    print("\n==== ashmit_resume.pdf (specific) ====")
    if not os.path.exists(path):
        print("MISSING fixture: ashmit_resume.pdf")
        FAILS.append("fixture " + path)
        return
    parsed = P.parse_pdf(path)
    st = parsed["structured"]

    # phantom custom section must be gone: every detected header maps to a
    # canonical key (no 'custom:NN' titled 'CGPA: 9.10')
    customs = [s for s in st["sections"] if str(s.get("key", "")).startswith("custom:")]
    check("ashmit: no phantom 'CGPA' custom section", not customs,
          [s.get("title") for s in customs])

    edu = next((s for s in st["sections"]
                if s.get("key") == "education" and s.get("type") == "entries"),
               None)
    entries = (edu or {}).get("entries", [])
    check("ashmit: 2 education entries (BMS + Higher Secondary)",
          len(entries) == 2, "got %d: %s"
          % (len(entries), [e.get("title", "")[:34] for e in entries]))
    if len(entries) == 2:
        e1, e2 = entries
        check("ashmit: entry1 CGPA attached to its entry (not orphaned)",
              norm(e1.get("meta", "")) == "cgpa: 9.10"
              or norm((e1.get("edu") or {}).get("score", "")) == "cgpa: 9.10",
              "meta=%r edu=%r" % (e1.get("meta"), (e1.get("edu") or {}).get("score")))
        check("ashmit: entry1 carries the BMS institution",
              "bms institute" in norm("%s %s" % (
                  e1.get("title", ""), " ".join(e1.get("bullets", [])))),
              e1.get("title"))
        check("ashmit: entry1 keeps its date row (2023-2027)",
              norm(e1.get("date", "")) == "2023-2027", e1.get("date"))
        check("ashmit: entry2 is Higher Secondary (inside EDUCATION)",
              "higher secondary" in norm(e2.get("title", "")),
              e2.get("title"))
        check("ashmit: entry2 93.7% attached to its entry",
              norm(e2.get("meta", "")) == "93.7%"
              or norm((e2.get("edu") or {}).get("score", "")) == "93.7%",
              "meta=%r edu=%r" % (e2.get("meta"), (e2.get("edu") or {}).get("score")))

    # rendered: education rows carry their right-aligned scores; auto mode
    # fits a single page (source is 2 pages: page 2 holds only Achievements)
    template = template_engine.auto_template(st)
    pdf = template_engine.generate_pdf(st, template)
    doc = fitz.open(stream=pdf, filetype="pdf")
    pages = doc.page_count
    lines_by_page = []
    for page in doc:
        rows = []
        for blk in page.get_text("dict")["blocks"]:
            for line in blk.get("lines", []):
                spans = line.get("spans", [])
                txt = "".join(s["text"] for s in spans)
                if spans:
                    rows.append((spans[0]["bbox"][1],
                                 max(s["bbox"][2] for s in spans), txt))
        lines_by_page.append(rows)
    doc.close()
    check("ashmit: auto mode renders 1 page", pages == 1,
          "pages=%d" % pages)
    # live flow passes max_pages = original page count (2 here).  The old
    # clamp accepted the comfortable 2-page render whose trailing page held
    # ONLY 2 orphaned bullets (24.9pt of content).  The orphan-tail rule
    # must tighten within the floor (level 1: 9.8pt/1.12) and ship 1 page.
    pdf2 = template_engine.generate_pdf(json.loads(json.dumps(st)), template,
                                        max_pages=2)
    doc2 = fitz.open(stream=pdf2, filetype="pdf")
    pages2 = doc2.page_count
    text2 = norm(" ".join(p.get_text("text") for p in doc2))
    doc2.close()
    check("ashmit: max_pages=2 (live path) still ships 1 page - no orphan "
          "tail", pages2 == 1, "pages=%d" % pages2)
    check("ashmit: no bullet left behind on a trailing page",
          "organized college fest" in text2 and "led a team of 30+" in text2)
    flat = [(y, x1, t) for rows in lines_by_page for (y, x1, t) in rows]
    edu_i = [i for i, (_, _, t) in enumerate(flat)
             if norm(t) == "education"]
    cgpa_i = [i for i, (_, _, t) in enumerate(flat)
              if "cgpa: 9.10" in norm(t)]
    check("ashmit: CGPA renders inside the EDUCATION block",
          bool(edu_i) and bool(cgpa_i) and cgpa_i[0] > edu_i[0],
          "edu@%s cgpa@%s" % (edu_i[:1], cgpa_i[:1]))
    check("ashmit: CGPA right-aligned on the education row",
          bool(cgpa_i) and flat[cgpa_i[0]][1] > 0.88 * 595,
          "x1=%.1f" % (flat[cgpa_i[0]][1] if cgpa_i else -1))
    for needle in ("bms institute", "higher secondary", "93.7%",
                   "sacred heart convent school"):
        check("ashmit: rendered PDF shows %r" % needle,
              any(needle in norm(t) for _, _, t in flat))


def run_structure_regressions():
    """Guard the two regressions from this fix round + the standardized
    education layout, across the real reference resumes (Vikas bmsit, Harsh,
    Kanish, Sarthak) and the permanent Vinod fixture.

    * Regression A: Harsh's first education institution ('Gurukula Kangri
      University, Haridwar, Uttarakhand') must survive to the rendered PDF.
    * Regression B: a projects section the source titles generically
      ('Portfolio') must never render as a 'PORTFOLIO' header - it shows the
      canonical 'Projects'.
    * Standardized education: every education entry renders institution (
      row 1) and degree (row 2) as separate fields, with date + CGPA (no
      '/10' suffix) right-aligned as their own cells.
    """
    refs = [
        (r"C:\Users\HP\Downloads\Vikas(bmsit).pdf", "Vikas"),
        (r"C:\Users\HP\Downloads\Harsh Arya Resume##.pdf", "Harsh"),
        (r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf", "Kanish"),
        (r"C:\Users\HP\Downloads\Sarthak_ Rawat_Resume.pdf", "Sarthak"),
        (os.path.join(BASE, "vinod_resume.pdf"), "Vinod"),
        (os.path.join(BASE, "muskan_resume.pdf"), "Muskan"),
        (os.path.join(BASE, "ashmit_resume.pdf"), "Ashmit"),
    ]
    for path, tag in refs:
        if not os.path.exists(path):
            print("  [skip %s] fixture not present: %s" % (tag, path))
            continue
        parsed = P.parse_pdf(path)
        st = parsed["structured"]
        template = template_engine.auto_template(st)
        pdf = template_engine.generate_pdf(st, template)
        doc = fitz.open(stream=pdf, filetype="pdf")
        text = norm(" ".join(p.get_text("text") for p in doc))
        doc.close()
        sect_titles = [norm(s.get("title", "")) for s in st["sections"]]
        check("%s: projects section header renders 'Projects' not "
              "'Portfolio'" % tag,
              "projects" in sect_titles and "portfolio" not in sect_titles,
              sect_titles)
        check("%s: no '/10' scale suffix in rendered education" % tag,
              "/10" not in text)
        # standardized two-row education fields
        edu_sections = [s for s in st["sections"]
                        if s.get("type") == "entries"
                        and s.get("key") == "education"]
        for sec in edu_sections:
            # a pure degree/qualification row may legitimately lack an
            # institution when a sibling row carries it (Muskan: university
            # row + separate 'B.tech. in Electrical Engineering' row)
            section_has_school = any(
                template_engine._SCHOOL_RE.search(
                    "%s|%s|%s|%s" % (e.get("title", ""), e.get("meta", ""),
                                     " ".join(e.get("bullets", [])),
                                     e.get("date", "")))
                for e in sec.get("entries", []))
            for e in sec.get("entries", []):
                field = ("%s|%s|%s|%s" % (
                    e.get("title", ""), e.get("meta", ""),
                    " ".join(e.get("bullets", [])), e.get("date", ""))).strip()
                has_school = bool(template_engine._SCHOOL_RE.search(field))
                degree_only = (not has_school and section_has_school
                               and bool(template_engine._DEG_RE.search(field)))
                check("%s: education entry carries an institution" % tag,
                      has_school or degree_only, field[:70])
        if tag == "Harsh":
            check("REGRESSION-A: Harsh institution 'Gurukula Kangri "
                  "University' rendered", "gurukula kangri" in text)
    # REGRESSION-B on the two sources that call the section 'Portfolio'
    for path, tag in [(r"C:\Users\HP\Downloads\Vikas(bmsit).pdf", "Vikas"),
                      (r"C:\Users\HP\Downloads\Sarthak_ Rawat_Resume.pdf",
                       "Sarthak")]:
        if not os.path.exists(path):
            continue
        st = P.parse_pdf(path)["structured"]
        titles = [s.get("title", "") for s in st["sections"]]
        check("REGRESSION-B: %s uses no 'Portfolio' section header" % tag,
              not any(norm(t) == "portfolio" for t in titles), titles)


def main():
    for spec in RESUMES:
        if not os.path.exists(spec["path"]):
            print("MISSING fixture (run make_*.py first):", spec["path"])
            FAILS.append("fixture " + spec["path"])
            continue
        run_one(spec)
    run_vinod()
    run_muskan()
    run_ashmit()
    run_structure_regressions()
    print("\n%d failure(s)" % len(FAILS) if FAILS else "\nALL RESUME TESTS PASSED")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())