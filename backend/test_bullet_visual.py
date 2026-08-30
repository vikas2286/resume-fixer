"""GATE B5 - PIXEL-LEVEL bullet glyph verification on the real Kanish resume.

xhtml2pdf draws <li> markers with Helvetica (no U+2022 glyph -> hollow
squares).  This gate does NOT trust text extraction: it renders the
generated PDF, finds bullet CONTENT rows geometrically, measures ink inside
each marker zone at 300 dpi, compares against same-row whitespace controls,
and asserts the vendored TTFs are really embedded.

Also proves B.4: font-awesome-solid / font-awesome-brands / resume-unicode
appear in the PDF font table, and saves PNG evidence:
    backend/_bullet_check_page.png   full rendered page (150 dpi)
    backend/_bullet_zoom.png         zoomed first bullet rows (300 dpi)
"""
import io
import os
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


PDF_SRC = r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf"
if not os.path.exists(PDF_SRC):
    print("SKIP: kanish reference not found")
    sys.exit(0)

MODE = os.environ.get("BMARK_MODE") or None
te.set_bullet_mode(MODE)
mode = te._bullet_mode()
print("bullet mode:", mode, "| icon fonts:", te.has_icon_fonts())

parsed = rp.parse_pdf(PDF_SRC)
pdf_bytes = te.generate_pdf(parsed["structured"], "classic")
doc = fitz.open(stream=pdf_bytes, filetype="pdf")

# ---- 1. embedded font proof -------------------------------------------------
all_fonts = {}
for pg in doc:
    for f in pg.get_fonts():
        all_fonts[f[3]] = f[0]
print("embedded font names:", sorted(all_fonts))
names_blob = "|".join(all_fonts)
check("DejaVu subset embedded (resume-unicode family)",
      "DejaVuSans" in names_blob, sorted(all_fonts))
check("Font Awesome Free Solid embedded",
      "FontAwesome6Free-Solid" in names_blob
      or "font-awesome-solid" in names_blob, sorted(all_fonts))
check("Font Awesome Brands embedded",
      "FontAwesome6Brands" in names_blob
      or "font-awesome-brands" in names_blob, sorted(all_fonts))

# STRONGEST bullet proof: every drawn U+2022 must be typed in the DejaVu
# subset (a missing-glyph square would stay Helvetica).
bullet_spans = []
for pg in doc:
    for blk in pg.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                if "\u2022" in sp.get("text", ""):
                    bullet_spans.append(sp)
print("drawn U+2022 spans:", len(bullet_spans),
      "fonts:", sorted({s["font"] for s in bullet_spans}))
if mode in ("native", "span"):
    check(">=8 real bullet glyphs drawn", len(bullet_spans) >= 8,
          len(bullet_spans))
    check("all bullet glyphs typed in DejaVu subset",
          bullet_spans
          and all("DejaVu" in s["font"] for s in bullet_spans),
          sorted({s["font"] for s in bullet_spans}))

# ---- 2. locate bullet content rows ------------------------------------------
page = doc[0]
W = page.rect.width
words = page.get_text("words")            # x0,y0,x1,y1,text,...
bullet_first_words = set()
for sec in parsed["structured"]["sections"]:
    if sec.get("type") != "entries":
        continue
    for e in sec["entries"]:
        for b in e.get("bullets", []):
            w = b.split()
            if len(w) >= 2:
                bullet_first_words.add(w[0].lower())
print("content-word probes:", sorted(bullet_first_words))

rows = []
for wd in words:
    x0, y0, x1, y1, txt = wd[0], wd[1], wd[2], wd[3], wd[4].lower().strip(",.:")
    if txt in bullet_first_words and 42 <= x0 <= 130 and y0 > 90:
        rows.append((y0, y1, x0))
# keep one row per y-band (dedupe same-line repeats)
rows.sort()
dedup = []
for r in rows:
    if dedup and abs(r[0] - dedup[-1][0]) < 3:
        continue
    dedup.append(r)
rows = dedup[:12]
print("bullet rows found:", len(rows))


def ink_fraction(rect):
    """fraction of dark pixels inside rect at 300 dpi."""
    pix = page.get_pixmap(clip=fitz.Rect(*rect), dpi=300)
    if pix.n >= 3:
        s = pix.samples
        total = pix.width * pix.height
        dark = sum(1 for i in range(0, len(s), pix.n)
                   if (s[i] + s[i + 1] + s[i + 2]) / 3 < 140)
        return dark / max(total, 1)
    return 0.0


marker_inks, control_inks = [], []
for y0, y1, x0 in rows:
    mz = (max(x0 - 13, 30), y0 + 0.6, x0 - 1.5, y1 - 0.6)
    cz = (W - 55, y0 + 0.6, W - 8, y1 - 0.6)
    mi, ci = ink_fraction(mz), ink_fraction(cz)
    marker_inks.append(mi)
    control_inks.append(ci)
    print("row y=%.1f marker-zone ink=%.4f control=%.4f"
          % (y0, mi, ci))

check("enough bullet rows located for stats", len(rows) >= 6,
      "found=%d" % len(rows))
inked = [m for m, c in zip(marker_inks, control_inks) if m > 0.01]
check(">=80%% of marker zones contain visible ink",
      len(marker_inks) >= 6 and len(inked) >= 0.8 * len(marker_inks),
      "inked=%d/%d" % (len(inked), len(marker_inks)))
mm = sum(marker_inks) / max(len(marker_inks), 1)
cm = sum(control_inks) / max(len(control_inks), 1)
check("marker ink clearly exceeds whitespace control", mm > cm + 0.02,
      "mean_marker=%.4f mean_control=%.4f" % (mm, cm))

# ---- 3. PNG evidence --------------------------------------------------------
out_png = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_bullet_check_page.png")
page.get_pixmap(dpi=150).save(out_png)
zoom_png = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_bullet_zoom.png")
if rows:
    top = min(r[0] for r in rows) - 8
    bot = rows[min(3, len(rows) - 1)][1] + 6
    page.get_pixmap(clip=fitz.Rect(25, max(top, 20), W - 25, bot),
                    dpi=300).save(zoom_png)
print("PNG saved:", out_png, "|", zoom_png)

doc.close()
print("\n%s (%d failure(s))" % ("GATE B5 GREEN" if fails == 0 else
                                "GATE B5 RED", fails))
sys.exit(1 if fails else 0)
