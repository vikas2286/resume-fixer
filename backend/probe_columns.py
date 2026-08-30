"""Dump same-y-band line geometry around suspected column fragments."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser as rp

PDF = r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf"
p = rp.parse_pdf(PDF)
print("multicolumn=%s has_tables=%s n_pages=%s"
      % (p.get("multicolumn"), p.get("has_tables"), p.get("n_pages")))
lines = p["lines"]

KEYS = ["freight", "on-site", "onsite", "tiger", "b.e", "b.tech",
        "coursework", "cgpa", "class", "2022", "2023", "2024", "2025"]


def band(ln):
    return (round(ln["y_top_pct"], 3), round(ln["y_bot_pct"], 3))


# print every line whose text hits a key WITH its band-mates
def overlap(a, b):
    return min(a[1], b[1]) - max(a[0], b[0])


hot = [i for i, l in enumerate(lines)
       if any(k in l["text"].lower() for k in KEYS)]
shown = set()
for i in sorted(hot):
    if i in shown:
        continue
    tgt = lines[i]
    b1 = (tgt["y_top_pct"], tgt["y_bot_pct"])
    mates = [(j, l) for j, l in enumerate(lines)
             if j != i and l.get("page") == tgt.get("page")
             and overlap(b1, (l["y_top_pct"], l["y_bot_pct"])) > 0.4]
    print("\n== band @y %.3f-%.3f  anchor=%r" % (b1[0], b1[1],
                                                 tgt["text"][:60]))
    grp = {i} | set(j for j, _ in mates)
    for j in sorted(grp | ({j for j, _ in mates})):
        l = lines[j]
        shown.add(j)
        print("   x0=%.3f x1=%.3f y=%.3f-%.3f bold=%s sz=%s %r"
              % (l["x0_pct"],
                 (l["bbox"][2] / 595.44 if len(l["bbox"]) > 2 else 0),
                 l["y_top_pct"], l["y_bot_pct"], l.get("bold"), l.get("size"),
                 l["text"][:70]))
