"""End-to-end smoke test (in-process): upload messy resume -> score ->
redflags -> JD match -> generate fixed PDF -> rescore.

Uses FastAPI's TestClient so no server needs to be running.
Usage: python test_e2e.py
"""
import os
import sys

# Make `backend/` importable so `import parser` etc. resolve.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402
import main as app_module  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(BASE, "messy_resume.pdf")
OUT = os.path.join(BASE, "test_fixed_output.pdf")


def print_score(label, s):
    print("%s overall=%s ats=%s visual=%s"
          % (label, s["overall"], s["ats"]["score"], s["visual"]["score"]))
    for chk in s["ats"]["checks"] + s["visual"]["checks"]:
        mark = "PASS" if chk["passed"] else "FAIL"
        print("  [%s] %-26s %s" % (mark, chk["check"], chk["reason"][:82]))


def run():
    assert os.path.exists(SAMPLE), "run make_sample_resume.py first"

    c = TestClient(app_module.app)
    h = c.get("/health").json()
    print("health:", h)

    with open(SAMPLE, "rb") as f:
        r = c.post("/upload", files={"file": ("messy_resume.pdf", f,
                                              "application/pdf")})
    assert r.status_code == 200, r.text
    up = r.json()
    sid = up["session_id"]
    print("upload ok  sid=%s  gemini=%s  pdf_engine=%s"
          % (sid, up["gemini_enabled"], h["pdf_engine"]))
    print_score("BEFORE", up["scores"])

    rf = c.post("/redflags/%s" % sid).json()
    print("redflags (%s): %d found" % (rf["engine"], len(rf["flags"])))
    for fl in rf["flags"][:3]:
        print("  - [%s] %s" % (fl["type"], fl["issue"]))

    jd = ("Senior Backend Engineer. Requirements: 5+ years Python experience, "
         "FastAPI, PostgreSQL, Docker, Kubernetes, AWS, REST APIs, microservices, "
         "CI/CD pipelines, Redis, strong system design, mentoring junior engineers, "
         "agile environment.")
    jm = c.post("/jdmatch/%s" % sid, json={"jd_text": jd}).json()
    print("jdmatch (%s): score=%d missing=%s"
          % (jm["engine"], jm["match_score"],
             [m["keyword"] for m in jm["missing"][:8]]))

    g = c.post("/generate/%s?template=modern" % sid)
    assert g.status_code == 200, g.text
    with open(OUT, "wb") as f:
        f.write(g.content)
    print("generate ok: %d bytes  before=%s after=%s -> %s"
          % (len(g.content), g.headers.get("X-Overall-Before"),
             g.headers.get("X-Overall-After"), OUT))

    rs = c.get("/rescore/%s" % sid).json()
    print_score("AFTER ", rs["after"])

    print("\nSCORE JUMP: %s -> %s  (%+d)"
          % (up["scores"]["overall"], rs["after"]["overall"],
             rs["after"]["overall"] - up["scores"]["overall"]))


if __name__ == "__main__":
    run()

