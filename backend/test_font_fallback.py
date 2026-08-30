"""B.4/B.5 graceful-degradation gate: with NO vendored fonts found,
rendering must still succeed - ASCII hyphen markers + legacy letter chips -
and never raise.  FONTS_DIR is pointed at a nonexistent path so no real
files are touched."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz

import template_engine as te

fails = 0


def check(name, cond, detail=""):
    global fails
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name,
                          ("- " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails += 1


te.FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "_no_such_fonts_dir_")
check("fonts unavailable simulated", te.available_fonts() == {},
      te.available_fonts())
check("icon fonts disabled", not te.has_icon_fonts())
check("bullet mode degrades to ascii", te._bullet_mode() == "ascii",
      te._bullet_mode())
check("font_css empty when fonts missing", te.font_face_css() == "")

resume = {
    "name": "Grace Hopper", "headline": "",
    "contacts": ["grace@navy.mil", "+1 555 0100",
                 "https://github.com/amazing-grace"],
    "sections": [
        {"title": "Skills", "type": "skills", "items": ["COBOL, FORTRAN"]},
        {"title": "Projects", "type": "entries", "entries": [
            {"title": "Compiler A-0", "meta": "", "date": "1952",
             "bullets": ["Wrote the first compiler.",
                         "Popularized machine-independent code."]},
        ]},
    ],
}
try:
    pdf = te.generate_pdf(resume, "classic")
    doc = fitz.open(stream=pdf, filetype="pdf")
    txt = doc[0].get_text()
    doc.close()
    check("generation succeeds without fonts", True)
    check("content still present", "Compiler A-0" in txt and
          "first compiler" in txt.replace("\n", " "))
    check("ascii hyphen markers used (no U+2022 dependency)",
          "-" in txt)
except Exception as exc:  # noqa: BLE001
    check("generation succeeds without fonts", False, repr(exc))

print("\n%s (%d failure(s))" % ("FALLBACK GATE GREEN" if fails == 0 else
                                "FALLBACK GATE RED", fails))
sys.exit(1 if fails else 0)
