"""Rect/entry-link map for the two Vikas reference PDFs."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser as rp

for PDF in (r"C:\Users\HP\Downloads\Vikas(bmsit).pdf",
            r"C:\Users\HP\Downloads\VIKAS_1by23is249_Bmsit.pdf"):
    if not os.path.exists(PDF):
        print("skip", PDF)
        continue
    p = rp.parse_pdf(PDF)
    print("\n=====", os.path.basename(PDF))
    for r in p["link_rects"]:
        print("   rect personal=%-5s %s" % (r["personal"], r["uri"][:70]))
    for l in p["lines"]:
        if l.get("link_uris"):
            print("   LINE %-40r %s" % (l["text"][:38], l["link_uris"]))
    for s in p["structured"]["sections"]:
        for e in s.get("entries", []):
            if e.get("link"):
                print("   ENTRY %-30r -> %s" % ((e.get("title") or "")[:28],
                                                e["link"]))
