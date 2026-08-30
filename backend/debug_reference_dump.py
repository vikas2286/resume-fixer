"""Dump structure of reference resumes: section order, header styling,
bullet style, contact block - to define the canonical output format."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser as rp  # noqa: E402

REFS = [
    r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf",
    r"C:\Users\HP\Downloads\Sarthak_ Rawat_Resume.pdf",
    r"C:\Users\HP\Downloads\ViKAS(1BY23IS249).pdf",
    r"C:\Users\HP\Downloads\Vikas(bmsit).pdf",
]

for path in REFS:
    print("#" * 78)
    print("### " + os.path.basename(path))
    print("#" * 78)
    try:
        parsed = rp.parse_pdf(path)
    except Exception as e:  # noqa: BLE001
        print("  FAILED:", e)
        continue
    st = parsed["structured"]
    print("pages=%d  fonts=%s" % (parsed["n_pages"], parsed["fonts"]))
    print("NAME: %r | HEADLINE: %r | CONTACTS: %s"
          % (st["name"], st.get("headline"), st["contacts"]))
    for sec in st["sections"]:
        t = sec.get("type")
        print("\n[%s] (%s)" % (sec["title"], t))
        if t == "paragraph":
            print("   " + sec["text"][:150])
        elif t == "skills":
            for it in sec["items"][:6]:
                print("   - " + it[:100])
        else:
            for e in sec.get("entries", [])[:5]:
                print("   * %s | %s | %s | bullets=%d"
                      % ((e.get("title") or "")[:50],
                         (e.get("meta") or "")[:30],
                         (e.get("date") or "")[:22],
                         len(e.get("bullets", []))))
                for b in e.get("bullets", [])[:2]:
                    print("       > " + b[:95])
    print()
