"""LIVE check against the running server: upload realistic_resume.pdf,
POST /generate (the exact call the fixed frontend makes), then assert the
returned PDF has clean data - no duplicate bullets, both project headers,
clean education, sane page count.
"""
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "realistic_resume.pdf")


def post_multipart(url, path):
    boundary = "----rfb"
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"%s\"\r\nContent-Type: application/pdf\r\n\r\n"
             % (boundary, os.path.basename(path))).encode()
            + open(path, "rb").read()
            + ("\r\n--%s--\r\n" % boundary).encode())
    req = urllib.request.Request(
        BASE + url, data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def post(url):
    req = urllib.request.Request(BASE + url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def main():
    up = post_multipart("/upload", SRC)
    sid = up["session_id"]
    print("upload ok  before overall =", up["scores"]["overall"])

    code, headers, pdf = post("/generate/%s?template=modern" % sid)
    print("generate:", code, len(pdf), "bytes |",
          get_h(headers, "X-Overall-Before"), "->",
          get_h(headers, "X-Overall-After"))
    assert code == 200

    import fitz
    doc = fitz.open(stream=pdf, filetype="pdf")
    text = norm(" ".join(p.get_text("text") for p in doc))

    checks = [
        ("AgentFlow heading", "AgentFlow" in text),
        ("ResumeRanker heading", "ResumeRanker" in text),
        ("no '· 1' glue", "\u00b7 1" not in text),
        ("CGPA preserved", "7.82" in text),
        ("education date preserved",
         "Sep 2023" in text and "2027" in text),
    ]
    bullets = [
        "Built multi-agent AI workflow automation platform serving 50k users",
        "Integrated 12+ LLM providers behind one unified interface",
        "Implemented agent-based resume scoring engine with ATS simulation",
    ]
    for b in bullets:
        n = text.count(norm(b))
        checks.append(("bullet exactly once: %s..." % b[:35], n == 1))
    checks.append(("page count <= original (%d)" % doc.page_count,
                   doc.page_count <= 1))

    fails = 0
    for name, ok in checks:
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1
    print("\nLIVE DATA CHECK: %s" % ("ALL PASSED" if fails == 0
                                     else "%d FAILED" % fails))
    return 1 if fails else 0


def get_h(headers, name):
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


if __name__ == "__main__":
    sys.exit(main())
