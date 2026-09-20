"""Regression test for the blank-'Your Name' placeholder-PDF bug (Sept 2026).

Root cause being guarded here: an image-only/scanned PDF yields zero
extractable text, the parser still returns a truthy-but-empty structured dict
({'name':'', 'sections':[]}), and the old truthiness guards in /generate let
it render the template's "Your Name" placeholder as a "successful" PDF.

This test synthesizes a genuine image-only PDF (text rasterized to a pixmap,
embedded with NO text layer) and asserts:
  1. /upload flags it (is_scanned=True)
  2. /rewrite  -> 422 with the scanned-PDF message
  3. /generate -> 422 with the scanned-PDF message, NEVER a 200 placeholder
  4. a normal text-based fixture still flows through untouched (is_scanned
     False, generate 200, real name in the output, no placeholder)

Run:  python test_scan_guard.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import llm_service  # noqa: E402
import main  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN_PDF = os.path.join(HERE, "_scan_only.pdf")
CONTROL = os.path.join(HERE, "muskan_resume.pdf")

# Offline + deterministic: no Gemini anywhere in this test.
_key_backup = llm_service.GEMINI_API_KEY
llm_service.GEMINI_API_KEY = ""
llm_service.structure_resume = lambda raw: None

_failures = []


def check(name, cond, extra=""):
    print(("[PASS] " if cond else "[FAIL] ") + name
          + (("  -> %s" % extra) if extra and not cond else ""))
    if not cond:
        _failures.append(name)


def make_image_only_pdf(path: str) -> None:
    """Render real resume-looking text, then embed it purely as an image so
    the resulting PDF has NO text layer (a scan, as far as any parser goes)."""
    src = fitz.open()
    page = src.new_page(width=612, height=792)
    y = 90
    for line, size in [("Muskan Pargal", 22),
                       ("muskanpargal74@gmail.com | 9596297327 | LinkedIn", 10),
                       ("PROFILE", 13),
                       ("Final-year Electrical Engineering student with "
                        "practical exposure", 10),
                       ("to power systems, substations and MATLAB/Simulink.",
                        10),
                       ("EXPERIENCE", 13),
                       ("POWERGRID - Jatwal Power Grid, 400/220 KV", 11),
                       ("Summer Internship - studied substation equipment",
                        10)]:
        page.insert_text((72, y), line, fontsize=size)
        y += 34 if size > 12 else 24
    pix = page.get_pixmap(dpi=150)  # rasterize: text becomes pixels
    out = fitz.open()
    out_page = out.new_page(width=612, height=792)
    out_page.insert_image(out_page.rect, pixmap=pix)
    out.save(path)
    out.close()
    src.close()


def upload(client: TestClient, path: str, cid: str) -> dict:
    with open(path, "rb") as f:
        r = client.post("/upload",
                        files={"file": (os.path.basename(path), f,
                                        "application/pdf")},
                        headers={"X-Client-Id": cid})
    assert r.status_code == 200, r.text
    return r.json()


def run() -> int:
    make_image_only_pdf(SCAN_PDF)

    # Sanity: the synthetic PDF really has no text layer.
    scan_text = "\n".join(p.get_text() for p in fitz.open(SCAN_PDF)).strip()
    check("synthetic PDF has no text layer", scan_text == "", repr(scan_text[:80]))

    client = TestClient(main.app)

    # ---- 1. upload flags the scan ------------------------------------------
    up = upload(client, SCAN_PDF, "cid-scan")
    check("upload: is_scanned=True for image-only PDF",
          up.get("is_scanned") is True, str(up.get("is_scanned")))
    sid = up["session_id"]

    # ---- 2. rewrite refuses -------------------------------------------------
    r = client.post("/rewrite/" + sid, headers={"X-Client-Id": "cid-scan"})
    check("rewrite: 422 for scanned upload", r.status_code == 422,
          str(r.status_code))
    check("rewrite: message names the scan problem",
          "scanned" in r.json().get("detail", ""), r.text[:120])

    # ---- 3. generate refuses - NEVER a placeholder PDF ----------------------
    r = client.post("/generate/" + sid + "?template=auto",
                    headers={"X-Client-Id": "cid-scan"})
    check("generate: 422 for scanned upload", r.status_code == 422,
          str(r.status_code))
    detail = r.json().get("detail", "") if r.status_code != 200 else ""
    check("generate: message names the scan problem",
          "scanned" in detail, detail[:160])

    # ---- 4. control: a real text fixture is untouched -----------------------
    up2 = upload(client, CONTROL, "cid-ctrl")
    check("control upload: is_scanned=False",
          up2.get("is_scanned") is False, str(up2.get("is_scanned")))
    r = client.post("/generate/" + up2["session_id"] + "?template=auto",
                    headers={"X-Client-Id": "cid-ctrl"})
    check("control generate: 200", r.status_code == 200, str(r.status_code))
    if r.status_code == 200:
        txt = "\n".join(p.get_text()
                        for p in fitz.open(stream=r.content, filetype="pdf"))
        check("control PDF contains the real name",
              "Muskan Pargal" in txt, txt[:120])
        check("control PDF has no placeholder", "Your Name" not in txt)

    # cleanup
    os.remove(SCAN_PDF)
    print()
    if _failures:
        print("SCAN-GUARD TESTS FAILED:", _failures)
        return 1
    print("ALL SCAN-GUARD TESTS PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    finally:
        llm_service.GEMINI_API_KEY = _key_backup