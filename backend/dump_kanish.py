"""Dump Kanish structured entries after A.1/A.2 fixes."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser as rp

PDF = r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf"
if not os.path.exists(PDF):
    sys.exit("missing pdf")
p = rp.parse_pdf(PDF)
print("\n--- lines carrying link_uris ---")
for l in p["lines"]:
    if l.get("link_uris"):
        print("   %-60r %s" % (l["text"][:58], l["link_uris"]))
for s in p["structured"]["sections"]:
    print("\n##", s["title"], "|", s["type"])
    if s["type"] == "entries":
        for e in s.get("entries", []):
            print("   E: %-46r meta=%-18r date=%-24r link=%r nbullets=%d"
                  % (e.get("title"), e.get("meta"), e.get("date"),
                     e.get("link"), len(e.get("bullets", []))))
            for b in e.get("bullets", []):
                print("        - %.78r" % b)
    elif s["type"] == "skills":
        for it in s.get("items", []):
            print("   S:", repr(it))
    else:
        t = s.get("text", "")
        print("   P:", repr(t[:120]))
