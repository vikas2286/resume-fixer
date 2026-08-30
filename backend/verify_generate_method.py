"""Live verification of the /generate method fix against the running server.

Reproduces what the browser sends:
  - GET  /generate/{sid}   -> must be 405 (the old client bug)
  - POST /generate/{sid}   -> must be 200 application/pdf (the fixed client)
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "messy_resume.pdf")


def request(method, url, data=None, content_type=None):
    req = urllib.request.Request(url, data=data, method=method)
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def get_header(headers, name):
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def main():
    # upload a resume to get a session
    boundary = "----rfboundary"
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"messy_resume.pdf\"\r\n"
             "Content-Type: application/pdf\r\n\r\n" % boundary).encode()
            + open(SAMPLE, "rb").read()
            + ("\r\n--%s--\r\n" % boundary).encode())
    code, headers, resp = request(
        "POST", BASE + "/upload", body,
        "multipart/form-data; boundary=%s" % boundary)
    assert code == 200, (code, resp[:200])
    sid = json.loads(resp)["session_id"]
    print("upload ok:", sid)

    url = "%s/generate/%s?template=classic" % (BASE, sid)

    # 1) The OLD buggy behaviour (GET) -> expect 405
    code, _, _ = request("GET", url)
    print("GET  /generate ->", code, "(expected 405 Method Not Allowed)")
    assert code == 405

    # 2) The FIXED behaviour (POST) -> expect 200 PDF
    code, headers, pdf = request("POST", url)
    ctype = get_header(headers, "Content-Type") or ""
    print("POST /generate ->", code, "|", ctype, "|", len(pdf), "bytes")
    print("     X-Overall-Before=%s X-Overall-After=%s"
          % (get_header(headers, "X-Overall-Before"),
             get_header(headers, "X-Overall-After")))
    assert code == 200 and "pdf" in ctype.lower() and len(pdf) > 1000

    print("\nMETHOD_FIX_VERIFIED: frontend POST matches backend route.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
