"""Check that GEMINI_API_KEY loads from backend/.env and reaches the API.
Prints status only - never prints the key."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm_service  # noqa: E402


def main():
    key = llm_service.GEMINI_API_KEY
    print("key present:", bool(key), "(length %d)" % len(key))
    print("model:", llm_service.MODEL_NAME)

    # --- shape diagnostics (no secret printed) ---------------------------
    if key:
        print("starts with 'AIza':", key.startswith("AIza"))
        print("contains whitespace/newline:", any(c.isspace() for c in key))
        print("contains quotes:", ('"' in key) or ("'" in key))
        print("contains commas:", "," in key)
        print("looks like OAuth token (ya29./AQ.):",
              key.startswith("ya29.") or key.startswith("AQ."))
    print("gemini_available:", llm_service.gemini_available())

    if not key:
        print("\nNo key found in backend/.env - set GEMINI_API_KEY=your_key")
        return 1

    # Live round-trip: one tiny rewrite call.
    out = llm_service.rewrite_bullet("was responsible for filing reports")
    print("\nlive call -> ", repr(out))
    if out and "was responsible" not in out.lower():
        print("GEMINI_OK - API responded and rewrote the bullet.")
        return 0
    print("GEMINI_CALL_FAILED - see error above (bad key / network).")
    return 1


if __name__ == "__main__":
    sys.exit(main())

