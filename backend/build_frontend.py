"""Build the frontend via subprocess (avoids shell quoting issues)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")
NODE_DIR = os.environ.get("NODE_BIN", r"C:\Program Files\nodejs")
_APPDATA_NPM = os.path.join(os.environ.get("APPDATA", ""), "npm")


def _env():
    env = os.environ.copy()
    env["PATH"] = NODE_DIR + os.pathsep + _APPDATA_NPM + os.pathsep + env.get("PATH", "")
    return env


def main():
    p = subprocess.run(["npm.cmd", "run", "build"], cwd=FRONTEND, text=True,
                       capture_output=True, env=_env(), timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    for ln in out.splitlines()[-25:]:
        print(ln)
    print("[build] exit=%d" % p.returncode)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
