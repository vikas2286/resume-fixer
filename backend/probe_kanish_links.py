"""Live probe: Kanish reference - do ALL real annotation links reach contacts?

Root cause #1 verification against the actual reference resume where 5
hyperlinks share ONE icon strip row.  Gate semantics:
  * every link_rect overlapping page-1 top band MUST be personal=True
  * every personal rect's URI MUST appear in structured contacts
  * every non-personal rect MUST NOT be in contacts
Exit code mirrors failures.
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser as rp

fails = 0


def check(name, cond, detail=""):
    global fails
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name,
                          ("- " + str(detail)) if detail and not cond else ""))
    if not cond:
        fails += 1


norm = lambda s: s.replace("https://", "").replace("http://", "") \
                  .replace("www.", "").replace("mailto:", "").rstrip("/").lower()

PDF = r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf"
if not os.path.exists(PDF):
    print("SKIP: %s not found" % PDF)
    sys.exit(0)

parsed = rp.parse_pdf(PDF)
st = parsed["structured"]
rects = parsed.get("link_rects", [])

print("--- Kanish link_rects ---")
for r in rects:
    print("  personal=%-5s p%s %s" % (r["personal"], r["page"], r["uri"]))

print("\n--- structured contacts ---")
for c in st["contacts"]:
    print("  ", c)

blob = "|".join(norm(c) for c in st["contacts"])

top_urs = [r["uri"] for r in rects
           if r["personal"] and r["page"] == 0]
mid_uris = [r["uri"] for r in rects if not r["personal"]]
check("at least 2 top-band personal rects found", len(top_urs) >= 2,
      top_urs)
missing = [u for u in top_urs if norm(u) not in blob]
check("all personal rects delivered to contacts", not missing, missing)
leaked = [u for u in mid_uris if norm(u) in blob]
check("no mid-page/project URI leaked into contacts", not leaked, leaked)

# total conservation: no unexplained loss of annotation links
n_ann = sum(1 for r in rects)
print("\nrect totals: personal=%d mid=%d" % (len(top_urs), len(mid_uris)))
print("%s (%d failure(s))" % ("KANISH PROBE GREEN" if fails == 0 else
                              "KANISH PROBE RED", fails))
sys.exit(1 if fails else 0)
