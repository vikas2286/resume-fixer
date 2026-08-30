"""LIVE end-to-end check for Harsh Arya's resume against the running server:
upload -> generate fixed PDF -> assert canonical reference structure."""
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"
SRC = r"C:\Users\HP\Downloads\Harsh Arya Resume##.pdf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_harsh_fixed.pdf")

boundary = "----rfb"
with open(SRC, "rb") as f:
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"harsh.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
             % boundary).encode() + f.read()
            + ("\r\n--%s--\r\n" % boundary).encode())
req = urllib.request.Request(
    BASE + "/upload", data=body, method="POST",
    headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
with urllib.request.urlopen(req, timeout=60) as r:
    up = json.loads(r.read())
sid = up["session_id"]
print("upload ok  sid=%s  BEFORE overall=%s" % (sid, up["scores"]["overall"]))

req = urllib.request.Request(BASE + "/generate/%s?template=classic" % sid,
                             data=b"", method="POST")
with urllib.request.urlopen(req, timeout=120) as r:
    pdf = r.read()
open(OUT, "wb").write(pdf)
print("generate ok: %d bytes" % len(pdf))

rs = json.loads(urllib.request.urlopen(
    BASE + "/rescore/%s" % sid, timeout=60).read())
print("AFTER overall=%s ats=%s visual=%s"
      % (rs["after"]["overall"], rs["after"]["ats"], rs["after"]["visual"]))

import fitz
doc = fitz.open(OUT)
text = " ".join(p.get_text("text") for p in doc)
print("pages:", doc.page_count)

fails = 0
def check(name, ok):
    global fails
    print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    fails += 0 if ok else 1

i_proj = text.find("Projects")
i_edu = text.find("Education")
i_codex = text.find("Codex")
i_btech = text.find("Bachelor of Technology")
check("single page", doc.page_count == 1)
# Harsh has no CGPA/percent -> weak academics -> canonical order
# Summary -> Skills -> Projects -> Education (Education demoted below Projects).
check("section order Summary->Skills->Projects->Education",
      -1 < i_proj < i_edu and text.find("Skills") < i_proj)
check("Codex present and inside Projects (between PROJECTS and EDUCATION)",
      i_codex != -1 and i_proj < i_codex < i_edu)
check("education has B.Tech near its own header and no Codex inside it",
      i_btech != -1 and i_btech < i_edu + 600 and
      text.find("Codex", i_edu) == -1)
# contacts: EVERY contact the parser extracted must render in the output
import re as _re
_flat = _re.sub(r"\s+", "", text).lower()
for _c in (up.get("structured") or {}).get("contacts", []):
    check("contact rendered: %s" % _c[:48],
          _re.sub(r"\s+", "", _c).lower() in _flat)
for h in ["AlgoZen", "GraphRAG Movie Recommendation Engine",
          "GeminiCodeReviewer"]:
    check("project title under Projects: " + h,
          text.find(h, i_proj) > i_proj)
check("skills populated", "Languages:" in text and "Generative AI" in text)
check("numbered project title rendered exactly once (as entry, not section)",
      text.count("3) GraphRAG Movie Recommendation Engine") == 1)

doc[0].get_pixmap(dpi=110).save(OUT.replace(".pdf", ".png"))
print("\nHARSH LIVE %s" % ("ALL PASSED" if fails == 0 else "%d FAILED" % fails))
sys.exit(1 if fails else 0)

