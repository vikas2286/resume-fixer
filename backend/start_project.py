"""Start the Resume Fixer stack: FastAPI backend (:8000) + Vite dev server (:5173).

Launches both detached (survives this script), logs to files, waits for
health checks, then prints the URLs. Idempotent - skips anything already
running.
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"

DETACHED = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


def log_path(name):
    return os.path.join(ROOT, name)


def spawn(cmd, cwd, logfile):
    lf = open(logfile, "ab")
    return subprocess.Popen(cmd, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT,
                            env=os.environ.copy(), creationflags=DETACHED,
                            close_fds=True)


def alive(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def wait_up(url, timeout_s=90):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if alive(url):
            return True
        time.sleep(1)
    return False


def main():
    pids = []

    # ---- backend ---------------------------------------------------------
    if not alive(BACKEND_URL + "/health"):
        print("starting backend ...", flush=True)
        pids.append(spawn([sys.executable, "-u", "-m", "uvicorn", "main:app",
                           "--host", "127.0.0.1", "--port", "8000"],
                          BACKEND, log_path("server.log")).pid)
    else:
        print("backend already running on :8000")

    if not wait_up(BACKEND_URL + "/health"):
        print("FAILED to start backend - see server.log")
        return 1
    try:
        with urllib.request.urlopen(BACKEND_URL + "/health", timeout=3) as r:
            print("backend OK :", r.read().decode())
    except Exception as e:
        print("backend health error:", e)

    # ---- frontend --------------------------------------------------------
    if not alive(FRONTEND_URL):
        print("starting frontend ...", flush=True)
        # Launch vite via node.exe directly - going through npm.cmd spawns a
        # cmd.exe batch job that gets killed by console cleanup events.
        node = os.path.join(r"C:\Program Files\nodejs", "node.exe")
        if not os.path.exists(node):
            from shutil import which
            node = which("node") or "node"
        vite_js = os.path.join(FRONTEND, "node_modules", "vite", "bin", "vite.js")
        pids.append(spawn([node, vite_js, "--host", "127.0.0.1",
                           "--port", "5173", "--strictPort"],
                          FRONTEND, log_path("dev.log")).pid)
    else:
        print("frontend already running on :5173")

    if not wait_up(FRONTEND_URL):
        print("FAILED to start frontend - see dev.log")
        return 1
    try:
        with urllib.request.urlopen(FRONTEND_URL, timeout=3) as r:
            body = r.read(200).decode(errors="replace")
        print("frontend OK:", "index.html served" if "<html" in body.lower()
              else body[:80])
    except Exception as e:
        print("frontend check error:", e)

    if pids:
        with open(os.path.join(ROOT, ".pids"), "w") as f:
            f.write("\n".join(str(p) for p in pids))
        print("pids saved to .pids:", pids)
        print("(stop later with: python backend/stop_project.py)")

    print("\n=========================================")
    print("  App      : http://localhost:5173")
    print("  API docs : http://localhost:8000/docs")
    print("=========================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
