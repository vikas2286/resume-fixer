"""GATE 1 - multi-URI tagging: no personal <-> project link crossover.

Reproduces the diagnosed Kanish root cause: five hyperlink annotations sit
over ONE shared header row.  Old code skipped already-tagged lines, so after
LinkedIn claimed the row every later rect came out personal=False and was
silently dropped from contacts.

Asserts:
  1. All 5 header-row URIs tag the single shared line and are personal=True.
  2. All 5 reach structured contacts.
  3. A mid-page "Link:" project bullet stays personal=False, lands on its
     ENTRY (not the contact header).
  4. Zero leakage in either direction.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz
import parser as rp

fails = 0


def check(name, cond, detail=""):
    global fails
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name,
                          ("- " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails += 1


def build_pdf(path):
    """One shared contact strip carrying 5 link rects + a mid-page project."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    f = lambda txt, pt, s, sz=9, fn="helv": page.insert_text(pt, txt,
                                                            fontsize=sz,
                                                            fontname=fn)
    W = lambda txt, sz, fn="helv": fitz.get_text_length(txt, fontname=fn,
                                                        fontsize=sz)

    f("KANISH KUMAR", (50, 42), 18)
    f("GITHUB      LINKEDIN      LEETCODE      PORTFOLIO      MAIL",
      (50, 62), 8)                                   # ONE shared row
    f("kanish.k@example.com | +91 98765 43210", (50, 78), 8)

    # Five rects over substrings of the SAME strip line.
    base_y, h = 54.5, 9.0
    segs = [("GITHUB", "https://github.com/kanish-s"),
            ("LINKEDIN", "https://www.linkedin.com/in/kanish-kumar"),
            ("LEETCODE", "https://leetcode.com/u/kanishk"),
            ("PORTFOLIO", "https://kanish.dev"),
            ("MAIL", "mailto:kanish.k@example.com")]
    x = 50.0
    strip_text = ("GITHUB      LINKEDIN      LEETCODE      "
                  "PORTFOLIO      MAIL")
    for label, uri in segs:
        idx = strip_text.index(label) if label != "MAIL" \
            else strip_text.rindex(label)
        lx = 50 + W(strip_text[:idx], 8)
        lw = W(label, 8)
        page.insert_link({"kind": fitz.LINK_URI, "uri": uri,
                          "from": fitz.Rect(lx, base_y, lx + lw, base_y + h)})

    f("SUMMARY", (50, 100), 11, fn="hebo")
    f("Builder obsessed with shipping fast under messy constraints.",
      (50, 114), 9)
    f("PROJECTS", (50, 142), 11, fn="hebo")
    f("Vision Detection System", (50, 158), 10, fn="hebo")
    f("- Built YOLO-based detection pipeline for retail cameras.", (56, 172), 9)
    f("- Reduced inference latency by 41% using TensorRT tuning.", (56, 186), 9)
    f("- Link:", (56, 200), 9)                      # mid-page label bullet
    lw_link = W("- Link:", 9)
    page.insert_link({"kind": fitz.LINK_URI,
                      "uri": "https://github.com/kanish/vision",
                      "from": fitz.Rect(56, 191.5, 56 + lw_link, 200.5)})
    doc.save(path)
    doc.close()


HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, "_gate_multilink.pdf")
build_pdf(PDF)

parsed = rp.parse_pdf(PDF)
st = parsed["structured"]
rects = parsed["link_rects"]

print("\n--- link_rects ---")
for r in rects:
    print("  personal=%-5s %s" % (r["personal"], r["uri"]))

# 1+2. every header rect personal and delivered as a contact
HEADER_URIS = ["github.com/kanish-s", "linkedin.com/in/kanish-kumar",
               "leetcode.com/u/kanishk", "kanish.dev",
               "kanish.k@example.com"]
for u in HEADER_URIS:
    r = next((r for r in rects if u in r["uri"]), None)
    check("header rect tagged: %s" % u, r is not None)
    check("header rect PERSONAL: %s" % u,
          bool(r and r["personal"]))
blob = "|".join(c.lower() for c in st["contacts"])
norm = lambda s: s.replace("https://", "").replace("http://", "") \
                  .replace("www.", "").rstrip("/").lower()
for u in HEADER_URIS:
    check("contact reaches header: %s" % u, norm(u) in blob, blob)

# 3. project link: not personal, attached to entry only
proj_uri = "https://github.com/kanish/vision"
pr = next((r for r in rects if r["uri"] == proj_uri), None)
check("project rect exists & NOT personal", bool(pr) and not pr["personal"],
      str(pr))
check("project URI absent from contacts", norm(proj_uri) not in blob, blob)

entries = []
for sec in st["sections"]:
    if sec.get("type") == "entries":
        for e in sec["entries"]:
            entries.append((sec["title"], e))
links_on_entries = [(t, e.get("link")) for t, e in entries if e.get("link")]
print("\n--- entry links ---")
for t, l in links_on_entries:
    print("  %-12s -> %s" % (t, l))

# 4. zero crossover
check("project entry carries its own link",
      any(l == proj_uri for _, l in links_on_entries), links_on_entries)
check("no header URI leaked onto an entry",
      all(not any(u in (l or "") for u in HEADER_URIS)
          for _, l in links_on_entries), links_on_entries)
shared = next((ln for ln in parsed["lines"]
               if len(ln.get("link_uris") or []) >= 5), None)
check("strip line carries all 5 URIs (multi-tag)",
      shared is not None,
      [ (l["text"][:40], l.get("link_uris")) for l in parsed["lines"][:4] ])

os.remove(PDF)
print("\n%s (%d failure(s))" % ("GATE 1 GREEN" if fails == 0 else
                                "GATE 1 RED", fails))
sys.exit(1 if fails else 0)
