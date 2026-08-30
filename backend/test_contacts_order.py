"""Verify issue fixes: conditional Education placement + complete contacts.

1. Vikas Gupta (CGPA 7.96 < 8.5) -> Education AFTER Projects in output.
2. Synthetic CGPA 9.0 -> Education BEFORE Summary in output.
3. Contacts: every link in the original (visible text + hyperlink
   annotations) appears in the generated PDF - count-in vs count-out.
"""
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

fails = 0


def check(name, cond, detail=""):
    global fails
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name,
                          ("- " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails += 1


HARSH = r"C:\Users\HP\Downloads\Harsh Arya Resume##.pdf"
VIKAS = r"C:\Users\HP\Downloads\VikasGupta_1BY23IS249.pdf"

print("===== 1/2: Education placement =====")


def render_order(pdf_path):
    doc = fitz.open(pdf_path)
    t = "\n".join(p.get_text() for p in doc)
    pages = doc.page_count
    doc.close()
    pos = {}
    for h in ["Summary", "Skills", "Projects", "Education"]:
        i = t.find(h)
        if i != -1:
            pos[h] = i
    return pos, t, pages


for tag, path in [("Vikas (CGPA<8.5)", VIKAS)]:
    parsed = rp.parse_pdf(path)
    cgpa, pct = te._academic_metrics(parsed["structured"]["sections"])
    pdf = te.generate_pdf(parsed["structured"], "classic",
                          os.path.join(os.path.dirname(__file__), "_ord.pdf"))
    pos, _, _ = render_order(os.path.join(os.path.dirname(__file__),
                                          "_ord.pdf"))
    print("  %s metrics: cgpa=%s pct=%s order=%s"
          % (tag, cgpa, pct, sorted(pos.items(), key=lambda kv: kv[1])))
    check("%s: CGPA parsed from PDF" % tag, cgpa is not None, "cgpa=%r" % cgpa)
    check("%s: CGPA below 8.5 threshold" % tag,
          cgpa is not None and cgpa < te.EDUCATION_TOP_CGPA)
    check("%s: Education AFTER Projects" % tag,
          "Education" in pos and "Projects" in pos
          and pos["Projects"] < pos["Education"])

synth = {
    "name": "Test Person", "headline": "", "contacts": [],
    "sections": [
        {"title": "Summary", "type": "paragraph", "text": "Summary text."},
        {"title": "Education", "type": "entries", "entries": [
            {"title": "B.Tech CSE", "meta": "CGPA: 9.0",
             "date": "2021 - 2025", "bullets": []}]},
        {"title": "Skills", "type": "skills", "items": ["Python, Go"]},
        {"title": "Projects", "type": "entries", "entries": [
            {"title": "Proj A", "meta": "", "date": "",
             "bullets": ["Built a thing."]}]},
    ],
}
html = te.render_html(synth, "classic")
heads = re.findall(r"<h2>(.*?)</h2>", html)
print("  synthetic CGPA-9.0 h2 order:", heads)
check("synthetic CGPA 9.0 -> Education before Summary",
      heads.index("Education") < heads.index("Summary"))

print("\n===== 3: contacts in vs out =====")
URL_TXT = re.compile(
    r"(?:https?://|www\.)[^\s|,\u00b7\u2022]+"
    r"|(?:github\.com|gitlab\.com|linkedin\.com|medium\.com)/[^\s|,\u00b7\u2022]+",
    re.IGNORECASE)


def original_links(path):
    """Every link the original exposes: visible text + link annotations."""
    found = set()
    doc = fitz.open(path)
    raw = "\n".join(p.get_text() for p in doc)
    for m in URL_TXT.finditer(raw.replace("\n", "")):
        found.add(m.group(0).rstrip("."))
    emails = set(m.group(0) for m in rp.EMAIL_RE.finditer(raw))
    phones = set()
    jm = rp._find_phone(raw.replace("\n", " "))
    if jm:
        phones.add(re.sub(r"\s+", " ", jm.group(0)))
    for page in doc:
        for lk in page.get_links():
            u = (lk or {}).get("uri")
            if u:
                u = re.sub(r"^(mailto:|tel:)", "", u.strip(),
                           flags=re.IGNORECASE)
                if not re.search(r"canva\.com|adobe\.com", u, re.I):
                    found.add(u.rstrip("."))
    doc.close()
    return found, emails, phones


for tag, path in [("HARSH", HARSH), ("VIKAS", VIKAS)]:
    want_links, want_emails, want_phones = original_links(path)
    parsed = rp.parse_pdf(path)
    st = parsed["structured"]
    got = st["contacts"]
    blob = re.sub(r"\s+", "", " ".join(got)).lower()

    # Project links now live on their ENTRIES (not the contact header) and
    # templates render labels instead of raw URLs - accept contacts,
    # entry.link values and bullet text as valid destinations.
    entry_links = []
    bullets_txt = []
    for sec in st["sections"]:
        if sec.get("type") == "entries":
            for e in sec["entries"]:
                if e.get("link"):
                    entry_links.append(e["link"])
                bullets_txt += e.get("bullets", []) or []
    link_blob = re.sub(r"\s+", "", "|".join(entry_links)).lower()
    bullet_blob = re.sub(r"\s+", "", " ".join(bullets_txt)).lower()

    def present(tok):
        t = re.sub(r"\s+", "", tok).lower()
        return (t in blob or t in link_blob
                or re.sub(r"^(https?://|www\.)", "", t) in link_blob
                or t in bullet_blob)

    missing = []
    for tok in sorted(want_emails | want_phones | want_links):
        norm = re.sub(r"^(https?://|www\.)", "", tok, flags=re.I)
        if not (present(tok) or present(norm)):
            missing.append(tok)
    print("  %s: in=%d (links=%d emails=%d phones=%d) out_contacts=%d "
          "entry_links=%d"
          % (tag, len(want_links) + len(want_emails) + len(want_phones),
             len(want_links), len(want_emails), len(want_phones),
             len(got), len(entry_links)))
    print("   contacts:", json.dumps(got, ensure_ascii=False))
    check("%s: every original contact/link preserved somewhere" % tag,
          not missing, "missing=%s" % missing)
    # rendered PDF must show them - as visible text OR clickable hrefs
    pdf_path = os.path.join(os.path.dirname(__file__), "_ct_%s.pdf" % tag)
    te.generate_pdf(st, "classic", pdf_path)
    doc = fitz.open(pdf_path)
    ptxt = re.sub(r"\s+", "", "\n".join(p.get_text() for p in doc)).lower()
    hrefs = ""
    for p_ in doc:
        for lk in p_.get_links():
            u = (lk or {}).get("uri")
            if u:
                hrefs += " " + u
    doc.close()
    hay = (ptxt + re.sub(r"\s+", "", hrefs).lower())
    miss_pdf = [tok for tok in want_emails | want_links
                if re.sub(r"\s+|^(https?://|www\.)", "", tok,
                          flags=re.I).lower() not in hay]
    check("%s: every email/link rendered or hyperlinked in output PDF"
          % tag, not miss_pdf, "missing=%s" % miss_pdf)

os.remove(os.path.join(os.path.dirname(__file__), "_ord.pdf"))
print("\n%s" % ("ALL PASSED" if fails == 0 else "%d FAILURES" % fails))
sys.exit(1 if fails else 0)