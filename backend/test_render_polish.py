"""Verify rendering polish: clickable link labels (no raw URL text),
selective metric-only bolding, education-placement debug branching."""
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz
import parser as rp
import template_engine as te
from html import unescape as _unescape

HERE = os.path.dirname(os.path.abspath(__file__))
fails = 0


def check(name, cond, detail=""):
    global fails
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name,
                          ("- " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails += 1


HARSH = r"C:\Users\HP\Downloads\Harsh Arya Resume##.pdf"
VIKAS = r"C:\Users\HP\Downloads\Vikas(bmsit).pdf"

# ---- 3. education-placement debug log --------------------------------------
print("===== education-placement debug log =====")
parsed_v = rp.parse_pdf(VIKAS)
cgpa, pct = te._academic_metrics(parsed_v["structured"]["sections"])
print("  parsed from Vikas(bmsit): cgpa=%r pct=%r" % (cgpa, pct))
check("Vikas CGPA parsed from PDF", cgpa is not None)

import contextlib
err = io.StringIO()
with contextlib.redirect_stderr(err):
    html_v = te.render_html(json.loads(json.dumps(
        parsed_v["structured"])), "classic")
log = err.getvalue()
print("  log:", log.strip().splitlines()[-1] if log.strip() else "<none>")
check("placement log printed",
      "[education-placement]" in log)
check("log shows correct WEAK branch for CGPA<8.5",
      "cgpa=%s" % cgpa in log and "END - after Achievements" in log, log)

synth_edu = {"title": "Education", "type": "entries", "entries": [
    {"title": "B.Tech CSE", "meta": "CGPA: 9.0", "date": "2021 - 2025",
     "bullets": []}]}
base_secs = [s for s in parsed_v["structured"]["sections"]
             if not te._is_education(s)]
err2 = io.StringIO()
with contextlib.redirect_stderr(err2):
    te.render_html({"name": "T", "contacts": [],
                    "sections": [synth_edu] + base_secs}, "classic")
log2 = err2.getvalue()
check("log shows TOP branch for CGPA 9.0",
      "cgpa=9.0" in log2 and "TOP - right after contacts" in log2,
      log2.strip().splitlines()[-1] if log2.strip() else "<none>")

# ---- 1. links as labels -----------------------------------------------------
print("\n===== links-as-labels (both resumes) =====")
for tag, path in [("HARSH", HARSH), ("VIKAS-BMSIT", VIKAS)]:
    st = json.loads(json.dumps(rp.parse_pdf(path)["structured"]))
    html = te.render_html(st, "classic")
    pdf_path = os.path.join(HERE, "_polish_%s.pdf" % tag)
    te.generate_pdf(st, "classic", pdf_path)
    doc = fitz.open(pdf_path)
    text = "\n".join(p.get_text() for p in doc)
    pages = doc.page_count
    doc.close()

    # visible text must contain no raw URLs
    visible_urls = re.findall(r"(?:https?://|www\.)\S+", text)
    check("%s: no raw URL visible in output PDF" % tag, not visible_urls,
          visible_urls[:3])

    # anchors exist with proper hrefs - PERSONAL links only
    anchors = re.findall(r'<a class="clink" href="([^"]+)">([^<]+)</a>', html)
    print("   contact anchors:", anchors)
    check("%s: contact links rendered as labeled anchors" % tag,
          len(anchors) >= 2 and all(a[1] and "<" not in a[1] for a in anchors))
    contact_labels = {lbl for _, lbl in anchors}
    check("%s: NO project links in contact header" % tag,
          not ({"VS Extension", "Demo"} & contact_labels),
          contact_labels)
    # icon chips before each item - MONOCHROME (no colored backgrounds)
    chips = re.findall(r'<span class="ico"[^>]*>([^<]+)</span>', html)
    print("   icon chips:", chips)
    check("%s: every header item has an icon chip" % tag,
          len(chips) >= len(anchors))
    mono_bad = re.findall(r'<span class="ico" style="[^"]*background', html)
    check("%s: icons are monochrome (no background fills)" % tag,
          not mono_bad, mono_bad[:3])
    check("%s: dot separators removed from header" % tag,
          "bull;" not in html.split("</style>")[-1].split("Summary")[0])

    # project "Link" bullets replaced by inline labeled chip
    check("%s: bare 'Link' bullets gone from output" % tag,
          not re.search(r"^Link$", text, re.M))
    proj_links = re.findall(r'<a class="entry-link" href="([^"]+)">'
                            r"([^<]+)</a>", html)
    print("   project links:", proj_links)
    if tag == "VIKAS-BMSIT":
        check("Vikas: both project hyperlinks attached to entries",
              len(proj_links) == 2, proj_links)
        labels = {lbl for _, lbl in proj_links}
        check("Vikas: project links use short labels (Demo/VS Extension)",
              labels <= {"Demo", "VS Extension", "Link"}, labels)

    # C.8 dual-path: bullets keep deterministic metric-only bolding, while
    # Summary paragraphs (type=paragraph) may carry LLM-picked key phrases.
    # Both must be verbatim-safe and modest in count.
    bullet_strongs = []
    for sec in st["sections"]:
        for e in sec.get("entries", []) or []:
            bullet_strongs += re.findall(
                r"<strong>(.*?)</strong>",
                " ".join(str(b) for b in e.get("bullets_html", [])))
    bad = [s for s in bullet_strongs
           if not re.fullmatch(r"[\d,]+(?:\.\d+)?\s*[%+x\u00d7]?", s or "")]
    check("%s: every <strong> in bullets is a short metric" % tag,
          not bad, "offenders=%s" % bad[:5])
    para_bad = []
    # render_html no longer mutates the caller's dict (the one-page
    # tightening loop needs pristine input); prep a private copy to obtain
    # the rendered summary HTML the same way the render pipeline does.
    secs_prepped = json.loads(json.dumps(st["sections"]))
    te._prep_entries(secs_prepped)
    for sec in secs_prepped:
        if sec.get("type") != "paragraph":
            continue
        txt = re.sub(r"\s+", " ", sec.get("text", "")).strip()
        htxt = re.sub(r"\s+", " ", str(sec.get("text_html", "")))
        p_strongs = re.findall(r"<strong>(.*?)</strong>", htxt)
        plain = _unescape(re.sub(r"</?strong>", "", htxt)).strip()
        if plain != txt:
            para_bad.append("mutated summary text")
        for s in p_strongs:
            if len(s) > 60 or s.lower() not in txt.lower():
                para_bad.append(s)
        if len(p_strongs) > 5:
            para_bad.append("too many bolds: %d" % len(p_strongs))
    check("%s: summary bolding is phrase-safe (C.8)" % tag,
          not para_bad, "offenders=%s" % para_bad[:5])
    # no bullet rendered fully bold (titles/headers MAY be bold by design)
    full_bold = [str(b)[:50] for sec in st["sections"]
                 for e in sec.get("entries", [])
                 for b in map(str, e.get("bullets_html", []))
                 if re.fullmatch(r"(<strong>.*</strong>|\s)*", b or " ")]
    check("%s: no bullet line is entirely bold" % tag, not full_bold,
          full_bold[:3])
    os.remove(pdf_path)

# ---- 5. right-aligned project link (table row, pinned right) ----------------
html_v2 = html  # last rendered (VIKAS-BMSIT)
check("project links use right-pinned table cells",
      '<td class="tr">' in html_v2
      and "td.tr { text-align: right" in html_v2.replace("\n", " "))
check("comfortable default spacing (line-height >= 1.4, project margin >= 8px)",
      "line-height: 1.45" in html_v2 and "margin-bottom: 10px" in html_v2)

# ---- exact section order -----------------------------------------------------
print("\n===== exact section order =====")
order_secs = [
    {"title": "Projects", "type": "entries", "entries": [
        {"title": "P", "meta": "", "date": "", "bullets": ["b."]}]},
    {"title": "Summary", "type": "paragraph", "text": "s"},
    {"title": "Experience", "type": "entries", "entries": [
        {"title": "E", "meta": "", "date": "", "bullets": ["b."]}]},
    {"title": "Achievements", "type": "entries", "entries": [
        {"title": "A", "meta": "", "date": "", "bullets": ["b."]}]},
    {"title": "Education", "type": "entries", "entries": [
        {"title": "D", "meta": "CGPA: 6.0", "date": "", "bullets": []}]},
]
o_low = [s["title"] for s in te._order_sections(
    json.loads(json.dumps(order_secs)))]
print("  weak-CGPA order:", o_low)
check("weak CGPA order: Summary,Skills?,Experience,Projects,Achievements,"
      "Education", o_low == ["Summary", "Experience", "Projects",
                             "Achievements", "Education"], o_low)
order_secs[4]["entries"][0]["meta"] = "CGPA: 9.0"
o_high = [s["title"] for s in te._order_sections(
    json.loads(json.dumps(order_secs)))]
print("  strong-CGPA order:", o_high)
check("strong CGPA order: Education first, then Summary..Achievements",
      o_high == ["Education", "Summary", "Experience", "Projects",
                 "Achievements"], o_high)

# ---- 4. hard one-page limit -------------------------------------------------
print("\n===== hard one-page limit =====")
bloated = {
    "name": "Bulk Resume", "headline": "", "contacts": [],
    "sections": [
        {"title": "Summary", "type": "paragraph",
         "text": "Dense summary. " * 40},
        {"title": "Projects", "type": "entries", "entries": [
            {"title": "Project %02d" % i, "meta": "Stack %d" % i,
             "date": "202%d - 202%d" % (i % 10, i % 10 + 1),
             "bullets": ["Did quantified work affecting %d%% of users "
                         "with %d+ services deployed." % (i, i * 3)
                         for _ in range(6)]}
            for i in range(12)]},
    ],
}
import contextlib as _cl
_err3 = io.StringIO()
with _cl.redirect_stderr(_err3):
    pdf = te.generate_pdf(json.loads(json.dumps(bloated)), "classic")
pages = te._page_count(pdf)
warned = "[one-page-limit]" in _err3.getvalue()
print("   bloated result: pages=%d warned=%s" % (pages, warned))
check("bloated resume: fits 1 page OR ships with explicit warning",
      pages == 1 or warned)
# tightening must never INCREASE page count
p0 = te._page_count(te.html_to_pdf_bytes(
    te.render_html(json.loads(json.dumps(bloated)), "classic", compact=0)))
p2 = te._page_count(te.html_to_pdf_bytes(
    te.render_html(json.loads(json.dumps(bloated)), "classic", compact=2)))
check("tightening does not increase page count (%d -> %d)" % (p0, p2),
      p2 <= p0)

print("\n%s" % ("ALL PASSED" if fails == 0 else "%d FAILURES" % fails))
sys.exit(1 if fails else 0)