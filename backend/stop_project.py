"""Stop servers on ports 8000/5173.

Strategy: kill pids recorded in .pids, THEN (fallback) taskkill any process
still LISTENING on the known ports - covers cases where the pid file was
overwritten by a later partial start.
"""
import os
import signal
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIDFILE = os.path.join(ROOT, ".pids")
PORTS = ["8000", "5173"]


def kill(pid):
    try:
        os.kill(int(pid), signal.SIGTERM)
        print("killed pid", pid)
        return True
    except OSError as e:
        print("could not kill pid", pid, "-", e)
        return False


def kill_pidfile():
    killed = 0
    if os.path.exists(PIDFILE):
        with open(PIDFILE) as f:
            for line in f:
                line = line.strip()
                if line.isdigit() and kill(line):
                    killed += 1
        os.remove(PIDFILE)
    return killed


def port_pids():
    """PIDs of processes LISTENING on our ports (via netstat -ano)."""
    out = subprocess.run(["netstat", "-ano"], capture_output=True,
                         text=True).stdout
    pids = set()
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) >= 5 and parts[-1].isdigit() and "LISTENING" in parts:
            local = parts[1]
            for port in PORTS:
                if local.endswith(":" + port):
                    pids.add(parts[-1])
    return pids


def main():
    killed = kill_pidfile()

    for pid in sorted(port_pids()):
        # taskkill /F is the reliable way to stop detached children on Windows
        r = subprocess.run(["taskkill", "/F", "/PID", pid],
                           capture_output=True, text=True)
        ok = r.returncode == 0
        print(("killed listener %s" % pid) if ok
              else ("failed to kill listener %s: %s" % (pid, r.stderr.strip())))
        killed += 1 if ok else 0

    if killed == 0:
        print("nothing to stop.")
    else:
        print("stopped %d process(es)." % killed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
