"""Stress test: run 5 never-seen synthetic resumes through the live HTTP
pipeline (upload -> score -> generate -> rescore) and dump raw evidence.
Report-only: no pass/fail gate - findings are reviewed by a human."""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz

import parser as rp
import make_stress_resumes as gen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8010
BASE = "http://127.0.0.1:%d" % PORT
LOG = os.path.join(BASE_DIR, "server.log")

FILES = ["stress_twocol.pdf", "stress_photo.pdf", "stress_headers.pdf",
         "stress_twopage.pdf", "stress_fresher.pdf"]

for f in FILES:
    if not os.path.exists(os.path.join(BASE_DIR, f)):
        gen._main()
        break


def log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def log_slice(start):
    with open(LOG, encoding="utf-8", errors="replace") as f:
        f.seek(start)
        return f.read()


def post_multipart(url, path):
    boundary = "----rfb"
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"%s\"\r\nContent-Type: application/pdf\r\n\r\n"
             % (boundary, os.path.basename(path))).encode()
            + open(path, "rb").read()
            + ("\r\n--%s--\r\n" % boundary).encode())
    req = urllib.request.Request(
        BASE + url, data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=%s"
                 % boundary})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

# ---- ensure server ---------------------------------------------------------
up = False
try:
    with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
        json.loads(r.read())
    up = True
except Exception:
    pass
if not up:
    print("[server] restarting on :%d ..." % PORT)
    subprocess.Popen(
        [sys.executable, "-W", "ignore", "-m", "uvicorn", "main:app",
         "--port", str(PORT)],
        cwd=BASE_DIR, stdout=subprocess.DEVNULL,
        stderr=open(LOG, "a", encoding="utf-8"))
    for _ in range(45):
        time.sleep(1)
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
                json.loads(r.read())
            up = True
            break
        except Exception:
            continue
print("[server] %s" % ("UP" if up else "DOWN"))
if not up:
    sys.exit(1)


for f in FILES:
    path = os.path.join(BASE_DIR, f)
    print("=" * 72)
    print("=== %s ===" % f)
    p = rp.parse_pdf(path)
    st = p["structured"]
    print("-- PARSE (ground truth, same parser as server)")
    print("   name=%r" % st.get("name"))
    print("   contacts=%s" % st.get("contacts"))
    for s in st.get("sections", []):
        print("   section %-16r type=%-10s entries=%d items=%d"
              % (s.get("title"), s.get("type"),
                 len(s.get("entries", []) or []),
                 len(s.get("items", []) or [])))
    print("   fonts=%s" % p.get("fonts"))
    print("   multicolumn=%s large_images=%s n_pages=%s"
          % (p.get("multicolumn"), p.get("large_images"), p.get("n_pages")))
    mark = log_size()
    up_j = post_multipart("/upload", path)
    sid = up_j["session_id"]
    sc = up_j.get("scores", {})
    print("-- UPLOAD (live API)")
    print("   ats=%s visual=%s overall=%s content=%s"
          % (sc.get("ats", {}).get("score"),
             sc.get("visual", {}).get("score"), sc.get("overall"),
             sc.get("content", {}).get("score")))
    for c in sc.get("ats", {}).get("checks", []):
        print("   ATS %-24s %-5s %s" % (
            c.get("check"), c.get("passed"),
            "" if c.get("passed") else "| " + c.get("reason", "")[:80]))
    for c in sc.get("visual", {}).get("checks", []):
        print("   VIS %-24s %-5s %s" % (
            c.get("check"), c.get("passed"),
            "" if c.get("passed") else "| " + c.get("reason", "")[:80]))
    fa = up_j.get("fix_assessment", {})
    print("   fix_mode=%s needs_major_fix=%s minor_flags=%d"
          % (up_j.get("fix_mode"), up_j.get("needs_major_fix"),
             len(fa.get("minor_suggestions", []))))
    print("   message=%r" % fa.get("message", "")[:140])
    req = urllib.request.Request(
        BASE + "/generate/%s?template=classic" % sid, data=b"",
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        pdf = r.read()
    out_p = os.path.join(BASE_DIR, "_stress_out_%s" % f)
    open(out_p, "wb").write(pdf)
    doc = fitz.open(out_p)
    sizes, tofu = {}, 0
    for pg_ in doc:
        for blk in pg_.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    if sp["size"] >= 8.5:
                        key = round(sp["size"], 1)
                        sizes[key] = sizes.get(key, 0) + 1
                    tofu += sp["text"].count("\ufffd")
        pg_.get_pixmap(dpi=130).save(
            os.path.join(BASE_DIR, "_stress_out_%s_p%d.png"
                         % (f.replace(".pdf", ""), pg_.number + 1)))
    print("-- GENERATE (live API)")
    print("   output pages=%d  body-font sizes=%s  replacement-chars=%d"
          % (len(doc), sorted(sizes.items()), tofu))
    doc.close()
    rs = get_json(BASE + "/rescore/%s" % sid)
    print("-- RESCORE (live API)")
    print("   ats=%s visual=%s overall=%s"
          % (rs.get("ats", {}).get("score"),
             rs.get("visual", {}).get("score"), rs.get("overall")))
    print("-- SERVER LOG (this resume's slice)")
    for l in log_slice(mark).splitlines():
        if l.startswith("["):
            print("   " + l[:150])

print("=" * 72)
for f in FILES:
    doc = fitz.open(os.path.join(BASE_DIR, f))
    doc[0].get_pixmap(dpi=110).save(
        os.path.join(BASE_DIR, "_stress_in_%s.png" % f.replace(".pdf", "")))
    doc.close()
print("input renders saved: _stress_in_*.png")
print("DONE")
