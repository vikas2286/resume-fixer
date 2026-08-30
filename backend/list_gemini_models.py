"""List Gemini models available to the configured API key."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm_service  # noqa: E402


def main():
    if not llm_service.GEMINI_API_KEY:
        print("no key"); return 1
    import google.generativeai as genai
    genai.configure(api_key=llm_service.GEMINI_API_KEY)
    print("models supporting generateContent:")
    for m in genai.list_models():
        methods = getattr(m, "supported_generation_methods", []) or []
        if "generateContent" in methods:
            print("  ", m.name.replace("models/", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
