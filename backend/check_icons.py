"""Header icon spot-check: which FONT draws each icon char in the rendered
Kanish header?  Proves real brand glyphs vs fallback text/tofu."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz

import parser as rp
import template_engine as te

PDF = r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf"
p = rp.parse_pdf(PDF)
pdf = te.generate_pdf(p["structured"], "classic")
doc = fitz.open(stream=pdf, filetype="pdf")
page = doc[0]

ICON_NAMES = {0xF0E0: "envelope(solid)", 0xF095: "phone(solid)",
              0xF09B: "github(brands)", 0xF0E1: "linkedin-in(brands)",
              0xF121: "code(solid)", 0xF0AC: "globe(solid)",
              0xF0C1: "link(solid)"}
print("--- header spans (y<100) ---")
icon_ok = {}
for blk in page.get_text("dict")["blocks"]:
    for ln in blk.get("lines", []):
        for sp in ln.get("spans", []):
            if sp["bbox"][1] > 100:
                continue
            t = sp["text"]
            print("font=%-34s size=%4.1f  %r" % (sp["font"], sp["size"],
                                                 t[:40]))
            for ch in t:
                cp = ord(ch)
                if cp in ICON_NAMES:
                    icon_ok[ICON_NAMES[cp]] = sp["font"]

print("\n--- verdict ---")
fails = 0
for name, font in sorted(icon_ok.items()):
    if "linkedin" in name:
        ok = "Brands" in font
    elif "solid" in name:
        ok = "Solid" in font or "brands" in name and "Brands" in font
    else:
        ok = "Solid" in font or "Brands" in font
    print("[%s] %s drawn by %s" % ("PASS" if ok else "FAIL", name, font))
    if not ok:
        fails += 1

# zoom PNG of the contact strip for the report
page.get_pixmap(clip=fitz.Rect(60, 85, page.rect.width - 60, 118),
                dpi=400).save(os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "_icons_zoom.png"))
print("saved _icons_zoom.png")
doc.close()
sys.exit(1 if fails else 0)
