"""Verify /rewrite actually rewrites bullets via Gemini and they land in the
generated PDF."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402
import main as app_module  # noqa: E402
import session_store  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(BASE, "messy_resume.pdf")


def main():
    c = TestClient(app_module.app)
    with open(SAMPLE, "rb") as f:
        up = c.post("/upload", files={"file": ("messy_resume.pdf", f)}).json()
    sid = up["session_id"]

    def bullets(structured):
        out = []
        for sec in structured.get("sections", []):
            if sec.get("type") == "entries":
                for e in sec.get("entries", []):
                    out += e.get("bullets", [])
        return out

    before = bullets(up["parsed"]["structured"])
    print("BEFORE rewrite (%d bullets):" % len(before))
    for b in before:
        print("   -", b)

    rw = c.post("/rewrite/%s" % sid)
    print("\n/rewrite status:", rw.status_code, "->", rw.json())

    g = c.post("/generate/%s?template=modern" % sid)
    print("/generate status:", g.status_code,
          "before=%s after=%s" % (g.headers.get("X-Overall-Before"),
                                  g.headers.get("X-Overall-After")))

    fixed = session_store.get(sid).get("fixed_structured") or {}
    after = bullets(fixed)
    print("\nAFTER rewrite (%d bullets now in the PDF):" % len(after))
    for b in after:
        print("   -", b)


if __name__ == "__main__":
    main()
