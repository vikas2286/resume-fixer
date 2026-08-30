"""LIVE verification against the running server using the real resume:
upload Vikas(bmsit).pdf, POST /generate (the exact call the fixed frontend
makes), then assert the returned PDF has clean data: each project header
present, every bullet exactly once, education clean, single page.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
SRC = r"C:\Users\HP\Downloads\Vikas(bmsit).pdf"


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
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, dict(r.headers), r.read()


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def main():
    up = post_multipart("/upload", SRC)
    sid = up["session_id"]
    print("upload ok (real resume)")

    code, headers, pdf = post("/generate/%s?template=classic" % sid)
    print("generate:", code, len(pdf), "bytes")
    assert code == 200

    import fitz
    doc = fitz.open(stream=pdf, filetype="pdf")
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "_srv_out.pdf"), "wb").write(pdf)
    text = norm(" ".join(p.get_text("text") for p in doc))

    fails = 0
    def check(name, ok):
        nonlocal fails
        print("[%s] %s" % ("PASS" if ok else "FAIL", name))
        fails += 0 if ok else 1

    # 1. every project header present, as a heading
    for h in ["Autonomous AI Code Editing Agent", "Hybrid Graph + Vector",
              "AI Agent Software Development System"]:
        check("project header present: " + h, h in text)

    # 2. no bullet appears twice
    bullets = [
        "Developed a 1,000+ line VS Code extension",
        "Integrated Gemini LLM API supporting 5-10",
        "Engineered compile-error detection loop",
        "Designed hybrid retrieval architecture",
        "Modeled 6 node types and 5 relationship types",
        "Implemented query-classification pipeline",
        "Built multi-agent AI workflow that autonomously",
        "Coordinated multi-agent pipeline using LangGraph",
    ]
    for b in bullets:
        check("bullet exactly once: %s..." % b[:40], text.count(norm(b)) == 1)

    # 3. education clean - no ".1" glue, date range intact
    check("no '1' orphan in education", "7.82" in text and "\u00b7 1" not in text)
    check("education date intact", "Sep 2023 - Sep 2027" in text)

    # 4. no contact glyph junk (no '#' or '\x83')
    check("no icon glyphs in contacts", "#" not in text.split("Summary")[0])

    # 5. page count unchanged (1 page)
    check("single page (1)", doc.page_count == 1)

    print("\nLIVE (real resume) %s" % ("ALL PASSED" if fails == 0
                                       else "%d FAILED" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())