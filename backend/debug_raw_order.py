"""Dump RAW extraction order (pre-merge) with coordinates for key lines,
and compare with visual (y-sorted) reading order."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz  # noqa: E402
import parser as rp  # noqa: E402

PDF = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\HP\Downloads\Harsh Arya Resume##.pdf"

KEYS = ["about me", "eduaction", "projects", "codex", "bachelor",
        "algozen", "graphrag movie", "working on it", "skills"]

doc = fitz.open(PDF)
raw = []
seen = set()
for pno, page in enumerate(doc):
    ph = page.rect.height or 792
    pw = page.rect.width or 612
    d = page.get_text("dict")
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            bbox = [round(v, 1) for v in line.get("bbox", [0, 0, 0, 0])]
            norm_text = rp.re.sub(r"\s+", " ", text).lower()
            key = (pno, norm_text, int(bbox[1] // 3))
            if key in seen:
                continue
            seen.add(key)
            main = max(spans, key=lambda s: s.get("size", 0))
            raw.append({
                "page": pno, "y": round(bbox[1] / ph * 100, 1),
                "x": round(bbox[0] / pw * 100, 1),
                "size": round(float(main.get("size", 0)), 1),
                "bold": "bold" in rp._norm_font(main.get("font")),
                "text": text,
                "_sortkey": key,
            })
doc.close()

print("=== RAW EXTRACTION ORDER (block order, post-dedupe, PRE-merge) ===")
print("idx   pg   x%    y%  size bold  text")
for i, l in enumerate(raw):
    mark = " <<<" if any(k in l["text"].lower() for k in KEYS) else ""
    print("%4d  %d  %5.1f %5.1f  %4.1f  %d   %.60s%s"
          % (i, l["page"], l["x"], l["y"], l["size"], l["bold"],
             l["text"], mark))

print("\n=== VISUAL READING ORDER (same lines, y-sorted per page) ===")
ysorted = sorted(raw, key=lambda l: (l["page"], l["y"], l["x"]))
for i, l in enumerate(ysorted):
    mark = " <<<" if any(k in l["text"].lower() for k in KEYS) else ""
    print("%4d  %d  %5.1f %5.1f  %4.1f  %d   %.60s%s"
          % (i, l["page"], l["x"], l["y"], l["size"], l["bold"],
             l["text"], mark))
