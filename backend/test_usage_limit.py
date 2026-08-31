"""Regression tests for the daily AI usage limiter (usage_limit.py + wiring).

The LLM layer is stubbed so the tests are deterministic and never touch the
network - the limiter's behavior is identical whether Gemini succeeds or not.

Run:  python test_usage_limit.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("AI_DAILY_LIMIT", "3")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-secret")
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

import llm_service  # noqa: E402
import main  # noqa: E402

# --- stub the LLM layer (no network) -----------------------------------------
llm_service.gemini_available = lambda: True
llm_service.rewrite_bullets = lambda bullets, context="": list(bullets)
llm_service.detect_red_flags = lambda text: [{"type": "stub", "quote": "q"}]
llm_service.match_jd = lambda text, jd: {"score": 50}
llm_service.summary_key_phrases = lambda text: []
llm_service.structure_resume = lambda raw: None

client = TestClient(main.app)
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "messy_resume.pdf")
ADMIN = "test-admin-secret"

_failures = []


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name
          + (("  -> " + extra) if extra and not cond else ""))
    if not cond:
        _failures.append(name)


def _upload(cid: str, admin_token: str = "") -> str:
    headers = {"X-Client-Id": cid}
    if admin_token:
        headers["X-Admin-Token"] = admin_token
    with open(FIXTURE, "rb") as f:
        r = client.post("/upload", files={"file": ("t.pdf", f, "application/pdf")},
                        headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def _rewrite(sid: str, cid: str, admin_token: str = ""):
    headers = {"X-Client-Id": cid}
    if admin_token:
        headers["X-Admin-Token"] = admin_token
    return client.post("/rewrite/" + sid, headers=headers)


def _usage(cid: str, admin_token: str = ""):
    headers = {"X-Client-Id": cid}
    if admin_token:
        headers["X-Admin-Token"] = admin_token
    return client.get("/usage", headers=headers).json()


def test_upload_score_never_limited():
    cid = "cid-free"
    for _ in range(6):
        sid = _upload(cid)
        assert client.get("/score/" + sid,
                          headers={"X-Client-Id": cid}).status_code == 200
    u = _usage(cid)
    check("upload/score unlimited (used==0)", u["used"] == 0, str(u))


def test_three_then_429():
    cid = "cid-cap"
    sid = _upload(cid)
    codes = [_rewrite(sid, cid).status_code for _ in range(4)]
    check("3 AI actions succeed", codes[:3] == [200, 200, 200], str(codes))
    r4 = _rewrite(sid, cid)
    check("4th blocked with 429", r4.status_code == 429, str(r4.status_code))
    detail = r4.json().get("detail", "")
    check("429 message mentions limit + reset",
          "Daily AI limit reached (3/3)" in detail and "resets at" in detail, detail)
    u = _usage(cid)
    check("usage shows 0 remaining",
          u["remaining"] == 0 and u["used"] == 3, str(u))


def test_generate_429_after_limit():
    cid = "cid-gen"
    sid = _upload(cid)
    for _ in range(3):
        assert _rewrite(sid, cid).status_code == 200
    r = client.post("/generate/" + sid + "?template=auto",
                    headers={"X-Client-Id": cid})
    check("generate blocked at limit (429)", r.status_code == 429,
          str(r.status_code))


def test_redflags_falls_back_to_rules():
    cid = "cid-rf"
    sid = _upload(cid)
    for _ in range(3):
        assert _rewrite(sid, cid).status_code == 200
    r = client.post("/redflags/" + sid, headers={"X-Client-Id": cid})
    body = r.json()
    check("redflags still 200 at limit", r.status_code == 200, str(r.status_code))
    check("redflags engine degraded to rules", body.get("engine") == "rules",
          str(body))
    check("redflags notice present",
          "Daily AI limit" in body.get("notice", ""), str(body))


def test_jdmatch_falls_back_to_rules():
    cid = "cid-jd"
    sid = _upload(cid)
    for _ in range(3):
        assert _rewrite(sid, cid).status_code == 200
    r = client.post("/jdmatch/" + sid,
                    json={"jd_text": "x" * 60}, headers={"X-Client-Id": cid})
    body = r.json()
    check("jdmatch still 200 at limit", r.status_code == 200, str(r.status_code))
    check("jdmatch engine degraded to rules", body.get("engine") == "rules",
          str(body))


def test_admin_bypass():
    cid = "cid-admin"
    sid = _upload(cid, ADMIN)
    codes = [_rewrite(sid, cid, ADMIN).status_code for _ in range(6)]
    check("admin unlimited (6 actions OK)", codes == [200] * 6, str(codes))
    u = _usage(cid, ADMIN)
    check("admin usage snapshot unlimited",
          u["admin"] is True and u["remaining"] is None and u["used"] == 0, str(u))
    r = client.post("/generate/" + sid + "?template=auto",
                    headers={"X-Client-Id": cid, "X-Admin-Token": ADMIN})
    check("admin generate works past limit", r.status_code == 200,
          str(r.status_code))


def test_wrong_admin_token_still_limited():
    cid = "cid-bad"
    sid = _upload(cid, "wrong-token")
    codes = [_rewrite(sid, cid, "wrong-token").status_code for _ in range(4)]
    check("wrong admin token limited like anyone", codes[-1] == 429, str(codes))


def test_usage_endpoint_fresh_client():
    u = _usage("cid-fresh")
    check("fresh client usage", u["used"] == 0 and u["remaining"] == 3
          and u["admin"] is False, str(u))


if __name__ == "__main__":
    for fn in [test_upload_score_never_limited, test_three_then_429,
               test_generate_429_after_limit, test_redflags_falls_back_to_rules,
               test_jdmatch_falls_back_to_rules, test_admin_bypass,
               test_wrong_admin_token_still_limited,
               test_usage_endpoint_fresh_client]:
        print("--", fn.__name__)
        fn()
    print()
    if _failures:
        print("USAGE-LIMIT TESTS FAILED:", _failures)
        sys.exit(1)
    print("ALL USAGE-LIMIT TESTS PASSED")

