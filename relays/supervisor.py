#!/usr/bin/env python3
"""Lightweight process supervisor for the three STT relays.

No systemd on macOS (the dev environment this was built on), and Docker
is a heavy lift for audio/model-downloading Python processes -- this is a
dependency-free supervisor: starts each relay as a subprocess, restarts
it with backoff if it crashes, captures stdout/stderr to per-engine log
files, and shuts down cleanly on SIGINT/SIGTERM. If this is ever deployed
to a real Linux server, each ManagedProcess maps 1:1 onto a systemd unit
(ExecStart=the same command, Restart=on-failure) -- this script is the
same idea without requiring systemd to exist.

Usage:
    python3 relays/supervisor.py                            # run all three
    python3 relays/supervisor.py whispercpp fasterwhisper    # just these
    python3 relays/supervisor.py status                      # is it running?
    python3 relays/supervisor.py stop                        # stop a running supervisor
"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
PID_FILE = ROOT / "supervisor.pid"

ENGINES = {
    "whispercpp": ROOT / "whispercpp_relay.py",
    "openaiwhisper": ROOT / "openai_whisper_relay.py",
    "fasterwhisper": ROOT / "fasterwhisper_relay.py",
    "parakeet": ROOT / "parakeet_relay.py",
}

RESTART_BACKOFF_SECONDS = [1, 2, 5, 10, 30]
MAX_RESTARTS_PER_ENGINE = 10


class ManagedProcess:
    def __init__(self, name, script):
        self.name = name
        self.script = script
        self.proc = None
        self.restart_count = 0
        self.given_up = False
        self._log_file = None

    def start(self):
        LOG_DIR.mkdir(exist_ok=True)
        self._log_file = open(LOG_DIR / f"{self.name}.log", "a")
        self.proc = subprocess.Popen(
            [sys.executable, str(self.script)],
            cwd=str(ROOT.parent),
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
        )
        print(f"[supervisor] started {self.name} (pid={self.proc.pid})", flush=True)

    def poll(self):
        return self.proc.poll() if self.proc else None

    def stop(self, timeout=10):
        if not self.proc or self.proc.poll() is not None:
            if self._log_file:
                self._log_file.close()
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[supervisor] {self.name} did not exit after SIGTERM, killing", flush=True)
            self.proc.kill()
            self.proc.wait()
        if self._log_file:
            self._log_file.close()


def _write_pid_file(engine_names):
    PID_FILE.write_text(json.dumps({"pid": os.getpid(), "engines": engine_names, "started": time.time()}))


def _remove_pid_file():
    PID_FILE.unlink(missing_ok=True)


def _running_supervisor():
    """Returns the PID-file contents if a supervisor process is alive,
    else cleans up a stale PID file and returns None."""
    if not PID_FILE.exists():
        return None
    try:
        data = json.loads(PID_FILE.read_text())
        os.kill(data["pid"], 0)  # raises if that PID isn't running
        return data
    except (ProcessLookupError, ValueError, KeyError, OSError, json.JSONDecodeError):
        PID_FILE.unlink(missing_ok=True)
        return None


def cmd_status():
    data = _running_supervisor()
    if not data:
        print("supervisor: not running", flush=True)
        return
    print(f"supervisor: running (pid={data['pid']}, engines={data['engines']}, since={time.ctime(data['started'])})", flush=True)


def cmd_stop():
    data = _running_supervisor()
    if not data:
        print("supervisor: not running", flush=True)
        return
    os.kill(data["pid"], signal.SIGTERM)
    print(f"sent SIGTERM to supervisor (pid={data['pid']})", flush=True)


def cmd_run(requested):
    if _running_supervisor():
        existing = _running_supervisor()
        print(f"supervisor already running (pid={existing['pid']}). Refusing to start a duplicate.", flush=True)
        sys.exit(1)

    names = requested or list(ENGINES.keys())
    for n in names:
        if n not in ENGINES:
            print(f"unknown engine: {n} (choices: {', '.join(ENGINES)})", flush=True)
            sys.exit(1)

    managed = [ManagedProcess(n, ENGINES[n]) for n in names]
    _write_pid_file(names)

    stopping = {"flag": False}

    def handle_signal(signum, frame):
        stopping["flag"] = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    for p in managed:
        p.start()

    try:
        while not stopping["flag"]:
            time.sleep(1)
            for p in managed:
                if p.given_up:
                    continue
                code = p.poll()
                if code is None:
                    continue
                if p.restart_count >= MAX_RESTARTS_PER_ENGINE:
                    p.given_up = True
                    print(f"[supervisor] {p.name} exceeded {MAX_RESTARTS_PER_ENGINE} restarts; giving up on it "
                          f"(other engines keep running -- check relays/logs/{p.name}.log)", flush=True)
                    continue
                backoff = RESTART_BACKOFF_SECONDS[min(p.restart_count, len(RESTART_BACKOFF_SECONDS) - 1)]
                print(f"[supervisor] {p.name} exited (code={code}); restarting in {backoff}s "
                      f"(attempt {p.restart_count + 1}/{MAX_RESTARTS_PER_ENGINE})", flush=True)
                time.sleep(backoff)
                p.restart_count += 1
                p.start()
    finally:
        print("[supervisor] shutting down...", flush=True)
        for p in managed:
            p.stop()
        _remove_pid_file()
        print("[supervisor] stopped.", flush=True)


def main():
    args = sys.argv[1:]
    if args and args[0] == "status":
        cmd_status()
    elif args and args[0] == "stop":
        cmd_stop()
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
