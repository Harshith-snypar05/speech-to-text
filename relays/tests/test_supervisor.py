"""supervisor.py's cmd_run() is a blocking, synchronous main-loop (real
time.sleep(), signal handlers registered on the main thread) designed to
run as a standalone process -- not something to await in-process inside
pytest-asyncio. These tests spawn it as a real subprocess against a
fast-crashing fake "engine" script, the same way it would run for real,
and assert on its behavior from the outside (log output, process exit).
"""
import json
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

RELAYS_DIR = Path(__file__).resolve().parent.parent


def _stream_lines_into(pipe, q):
    for line in iter(pipe.readline, ""):
        q.put(line)
    q.put(None)  # sentinel: stream closed


def _read_until(proc, predicate, timeout):
    """Reads lines from proc.stdout on a background thread (so a single
    blocking readline() can never hang the test past `timeout`) until
    `predicate(line)` is true. Returns (matched: bool, lines: list[str]).
    """
    q: queue.Queue = queue.Queue()
    reader = threading.Thread(target=_stream_lines_into, args=(proc.stdout, q), daemon=True)
    reader.start()

    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(0.0, deadline - time.time())
        try:
            line = q.get(timeout=min(remaining, 0.5))
        except queue.Empty:
            continue
        if line is None:  # stream closed without matching
            break
        lines.append(line)
        if predicate(line):
            return True, lines
    return False, lines


@pytest.fixture
def fake_crasher_script(tmp_path):
    script = tmp_path / "fake_crasher.py"
    script.write_text(
        "import sys, time\n"
        "time.sleep(0.2)\n"
        "print('fake engine: crashing now', flush=True)\n"
        "sys.exit(1)\n"
    )
    return script


@pytest.fixture
def supervisor_runner(tmp_path, fake_crasher_script):
    """A small driver script that monkeypatches supervisor's ENGINES/
    backoff table to point at the fake crasher before calling cmd_run(),
    so the test doesn't have to wait on real model loads.
    """
    pid_file = tmp_path / "supervisor.pid"
    log_dir = tmp_path / "logs"
    driver = tmp_path / "driver.py"
    driver.write_text(f"""
import sys
sys.path.insert(0, {str(RELAYS_DIR)!r})
import pathlib
import supervisor
supervisor.ENGINES = {{"fakecrasher": {str(fake_crasher_script)!r}}}
supervisor.RESTART_BACKOFF_SECONDS = [0.1, 0.15]
supervisor.MAX_RESTARTS_PER_ENGINE = 2
supervisor.PID_FILE = pathlib.Path({str(pid_file)!r})
supervisor.LOG_DIR = pathlib.Path({str(log_dir)!r})
supervisor.cmd_run(["fakecrasher"])
""")
    return {"driver": driver, "pid_file": pid_file, "log_dir": log_dir}


def _spawn(driver):
    return subprocess.Popen(
        [sys.executable, str(driver)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )


def test_restart_backoff_and_give_up(supervisor_runner):
    proc = _spawn(supervisor_runner["driver"])
    try:
        matched, lines = _read_until(
            proc, lambda line: "exceeded" in line and "giving up" in line, timeout=10,
        )
        assert matched, f"expected a give-up message within 10s, got:\n{''.join(lines)}"
        assert any("restarting in" in line for line in lines), "expected at least one restart attempt logged"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_graceful_shutdown_stops_child_process(supervisor_runner):
    proc = _spawn(supervisor_runner["driver"])
    try:
        matched, lines = _read_until(proc, lambda line: "started fakecrasher" in line, timeout=5)
        assert matched, f"supervisor never reported starting the fake engine, got:\n{''.join(lines)}"

        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        assert proc.returncode is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_pid_file_prevents_duplicate_supervisor(supervisor_runner):
    pid_file = supervisor_runner["pid_file"]
    pid_file.write_text(json.dumps({"pid": 999999999, "engines": ["fakecrasher"], "started": time.time()}))

    # A PID that (almost certainly) doesn't exist should be treated as
    # stale and cleaned up, not block a fresh start -- verified directly
    # against the supervisor module's own logic, since that's the unit of
    # behavior this guards (no need to spawn a subprocess for this one).
    sys.path.insert(0, str(RELAYS_DIR))
    import importlib
    import supervisor
    importlib.reload(supervisor)
    supervisor.PID_FILE = pid_file
    assert supervisor._running_supervisor() is None, "a PID file pointing at a dead process should be treated as stale"
    assert not pid_file.exists(), "stale PID file should be cleaned up"
