"""D.9: clean server restart + fix-mode log assertions + final sign-off
renders for all three resumes through the RUNNING server (the same HTTP
calls the frontend makes)."""
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8010
BASE = "http://127.0.0.1:%d" % PORT
LOG = os.path.join(BASE_DIR, "server.log")

RESUMES = [
    ("Kanish", r"C:\Users\HP\Downloads\Kanish_MyResume (4).pdf", "MINOR"),
    ("Vikas-Gupta", r"C:\Users\HP\Downloads\Vikas(bmsit).pdf", "MINOR"),
    # the messy A/B demo resume - the canonical FULL FIX target
    ("Harsh-messy", os.path.join(BASE_DIR, "messy_resume.pdf"), "FULL FIX"),
]

HARSH_SRC = os.path.join(BASE_DIR, "harsh_resume.pdf")
if not os.path.exists(HARSH_SRC):
    subprocess.run([sys.executable, "-W", "ignore",
                    os.path.join(BASE_DIR, "make_harsh_sample.py")],
                   cwd=BASE_DIR, check=True, capture_output=True)

# ---- 1. clean restart (kill ONLY uvicorn servers - never this process) -----
subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -match 'uvicorn' } | "
     "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
    capture_output=True)
subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
     "Where-Object { $_.CommandLine -match 'main:app' } | "
     "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
    capture_output=True)
time.sleep(1.5)
out = open(os.path.join(BASE_DIR, "server_out.log"), "w", encoding="utf-8")
err = open(LOG, "w", encoding="utf-8")
subprocess.Popen(
    [sys.executable, "-W", "ignore", "-m", "uvicorn", "main:app",
     "--port", str(PORT)],
    cwd=BASE_DIR, stdout=out, stderr=err)
print("uvicorn starting on :%d (fresh process)..." % PORT)

up = False
for _ in range(45):
    time.sleep(1)
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
            json.loads(r.read())
        up = True
        break
    except Exception:
        continue
print("[health] %s" % ("UP" if up else "DOWN"))
if not up:
    print(open(LOG, encoding="utf-8", errors="replace").read()[-1500:])
    sys.exit(1)


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


fails = []
results = []
for label, path, expect in RESUMES:
    mark = log_size()
    up_json = post_multipart("/upload", path)
    sid = up_json["session_id"]
    req = urllib.request.Request(
        BASE + "/generate/%s?template=classic" % sid, data=b"",
        method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        pdf = r.read()
    new_log = log_slice(mark)
    fix_lines = [l for l in new_log.splitlines() if "[fix-mode]" in l
                 and "->" in l]
    got = fix_lines[-1].split("->")[-1].strip() if fix_lines else "(none)"
    ok = expect in got
    print("[%s] fix-mode -> %-45s %s" % (
        "PASS" if ok else "FAIL", got, "" if ok else "(expected %s)"
        % expect))
    if not ok:
        fails.append(label)
    results.append((label, sid, pdf, got))

# ---- final sign-off renders -------------------------------------------------
for label, sid, pdf, _m in results:
    p = os.path.join(BASE_DIR, "_final_%s.pdf" % label.lower())
    open(p, "wb").write(pdf)
    doc = fitz.open(p)
    doc[0].get_pixmap(dpi=150).save(
        os.path.join(BASE_DIR, "_final_%s.png" % label.lower()))
    doc.close()
    print("saved _final_%s.pdf + _final_%s.png" % (label.lower(),
                                                   label.lower()))

print("\n== D.9: %s ==" % ("GREEN - 0 failures" if not fails
                           else "RED: %s" % fails))
sys.exit(1 if fails else 0)
