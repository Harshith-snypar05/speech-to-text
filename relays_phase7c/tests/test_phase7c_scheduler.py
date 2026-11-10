"""Phase 7C regression tests: finals-first scheduling, partial backpressure, final deadlines,
dropped-final accounting. Scheduler tests use a gated fake run_sync on a real single-thread
executor (no model); session tests drive run_speaker_session with a scheduled fake engine.
"""
import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import core.flush_diagnostics as flush_diag
from core.scheduler import FinalExpired, InferenceScheduler, JobTicket
from core.session_manager import SessionRegistry
from core.speaker_session import run_speaker_session
from engines.base_engine import TranscriptionEngine

from .conftest import FakeEngine, FakeWebSocket
from .test_speaker_session import _buf


class Gated:
    """run_sync double: records execution order; a sample listed in `gates` blocks until released."""

    def __init__(self, gates=(), text=lambda s: f"text:{s}", sleep_s=0.0):
        self.order: list = []
        self.started: dict = {}
        self.release: dict = {g: threading.Event() for g in gates}
        self.text = text
        self.sleep_s = sleep_s
        self._lock = threading.Lock()
        self.block_all = threading.Event()   # when .block_set is True every call waits for block_all
        self.block_set = False

    def __call__(self, sample):
        with self._lock:
            self.order.append(sample)
            self.started.setdefault(sample, threading.Event()).set()
        if self.block_set:
            assert self.block_all.wait(10), "test gate never released"
        if sample in self.release:
            assert self.release[sample].wait(10), "test gate never released"
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return self.text(sample)

    def wait_started(self, sample):
        with self._lock:
            ev = self.started.setdefault(sample, threading.Event())
        return ev


@pytest.fixture
def executor():
    ex = ThreadPoolExecutor(max_workers=1)
    yield ex
    ex.shutdown(wait=False)


async def _until(pred, timeout=3.0):
    t0 = time.monotonic()
    while not pred():
        assert time.monotonic() - t0 < timeout, "condition never became true"
        await asyncio.sleep(0.005)


async def _start_blocker(sched, run, name="blocker"):
    """Occupies the worker with a gated final so later requests queue up."""
    task = asyncio.create_task(sched.submit_final(name, "blk"))
    await _until(lambda: run.wait_started(name).is_set())
    return task


# ------------------------------------------------------------- final priority
async def test_final_runs_before_queued_partials(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    p1 = asyncio.create_task(sched.submit_partial("p1", "s1"))
    p2 = asyncio.create_task(sched.submit_partial("p2", "s2"))
    await asyncio.sleep(0.02)
    f = asyncio.create_task(sched.submit_final("f", "s3"))   # arrives AFTER the partials
    await asyncio.sleep(0.02)
    run.release["blocker"].set()
    assert await f == "text:f"
    await blocker
    await p1
    await p2
    assert run.order == ["blocker", "f", "p1", "p2"], run.order


async def test_running_job_is_not_preempted(executor):
    run = Gated(gates=["p1"])
    sched = InferenceScheduler(run, executor)
    p = asyncio.create_task(sched.submit_partial("p1", "s1"))
    await _until(lambda: run.wait_started("p1").is_set())
    f = asyncio.create_task(sched.submit_final("f", "s2"))
    await asyncio.sleep(0.05)
    assert not f.done(), "final must wait for the running partial to finish"
    run.release["p1"].set()
    assert await f == "text:f"
    assert await p == "text:p1"
    assert run.order == ["p1", "f"]


async def test_same_speaker_finals_keep_order(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    f1 = asyncio.create_task(sched.submit_final("a1", "spk"))
    await asyncio.sleep(0.01)
    other = asyncio.create_task(sched.submit_final("b1", "other"))
    await asyncio.sleep(0.01)
    f2 = asyncio.create_task(sched.submit_final("a2", "spk"))
    await asyncio.sleep(0.01)
    run.release["blocker"].set()
    await asyncio.gather(blocker, f1, other, f2)
    assert run.order == ["blocker", "a1", "b1", "a2"]
    assert run.order.index("a1") < run.order.index("a2")


# ------------------------------------------------------------ partial handling
async def test_partial_runs_when_no_final_waiting(executor):
    run = Gated()
    sched = InferenceScheduler(run, executor)
    assert await sched.submit_partial("p", "s1") == "text:p"
    assert sched.stats["partials_requested"] == 1 and sched.stats["partials_executed"] == 1
    assert sched.stats["partials_skipped"] == 0


async def test_partial_skipped_when_final_waiting(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    f = asyncio.create_task(sched.submit_final("f", "s1"))
    await asyncio.sleep(0.02)
    assert await sched.submit_partial("p", "s2") is None
    assert sched.stats["partials_skipped_by_reason"] == {"final_waiting": 1}
    run.release["blocker"].set()
    await asyncio.gather(blocker, f)
    assert "p" not in run.order


async def test_partial_skipped_when_same_speaker_already_pending(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    p1 = asyncio.create_task(sched.submit_partial("p1", "s1"))
    await asyncio.sleep(0.02)
    assert await sched.submit_partial("p1b", "s1") is None   # same speaker still queued
    assert sched.stats["partials_skipped_by_reason"] == {"same_speaker_pending": 1}
    run.release["blocker"].set()
    await asyncio.gather(blocker, p1)
    assert run.order == ["blocker", "p1"]
    assert await sched.submit_partial("p1c", "s1") == "text:p1c"  # nothing pending any more


async def test_partial_backlog_is_bounded_by_speakers(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    tasks = [asyncio.create_task(sched.submit_partial(f"p{i}", "s1")) for i in range(50)]
    await asyncio.sleep(0.05)
    assert len(sched._partials) == 1
    assert sched.stats["partials_skipped"] == 49
    run.release["blocker"].set()
    results = await asyncio.gather(blocker, *tasks)
    assert sum(r is not None for r in results[1:]) == 1


async def test_queued_partial_dropped_when_own_final_arrives(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    p = asyncio.create_task(sched.submit_partial("p", "s1"))
    await asyncio.sleep(0.02)
    f = asyncio.create_task(sched.submit_final("f", "s1"))
    await asyncio.sleep(0.02)
    assert await p is None
    assert sched.stats["partials_skipped_by_reason"] == {"superseded_by_final": 1}
    run.release["blocker"].set()
    await asyncio.gather(blocker, f)
    assert run.order == ["blocker", "f"]


async def test_stale_partial_dropped_unrun(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor, partial_max_queue_age=0.05)
    blocker = await _start_blocker(sched, run)
    p = asyncio.create_task(sched.submit_partial("p", "s1"))
    await asyncio.sleep(0.15)
    run.release["blocker"].set()
    await blocker
    assert await p is None
    assert sched.stats["partials_skipped_by_reason"] == {"stale_in_queue": 1}
    assert "p" not in run.order


async def test_partials_not_starved_without_final_pressure(executor):
    run = Gated(sleep_s=0.01)
    sched = InferenceScheduler(run, executor)
    for i in range(10):
        assert await sched.submit_partial(f"p{i}", f"s{i % 3}") == f"text:p{i}"
    assert sched.stats["partials_executed"] == 10 and sched.stats["partials_skipped"] == 0


# ------------------------------------------------------------ final deadlines
async def test_expired_final_never_started(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    ticket = JobTicket("final", "s1")
    f = asyncio.create_task(sched.submit_final("late", "s1", deadline=time.monotonic() + 0.05, ticket=ticket))
    await asyncio.sleep(0.15)          # deadline passes while still queued behind the running blocker
    run.release["blocker"].set()
    with pytest.raises(FinalExpired):
        await f
    await blocker
    assert "late" not in run.order, "an expired final must never be handed to the worker"
    assert ticket.state == "expired_in_queue" and ticket.dispatch_count == 0
    assert sched.stats["finals_expired_in_queue"] == 1 and sched.stats["finals_dispatched"] == 1


async def test_final_with_deadline_already_passed_at_submit(executor):
    run = Gated()
    sched = InferenceScheduler(run, executor)
    with pytest.raises(FinalExpired):
        await sched.submit_final("x", "s1", deadline=time.monotonic() - 1)
    assert run.order == []


async def test_caller_timeout_while_queued_is_accounted_as_expired(executor):
    """wait_for fires at the deadline while the final is queued: removed from the queue, not run."""
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    ticket = JobTicket("final", "s1")
    deadline = time.monotonic() + 0.1
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sched.submit_final("late", "s1", deadline=deadline, ticket=ticket), 0.1)
    assert ticket.state == "expired_in_queue"
    assert len(sched._finals) == 0
    run.release["blocker"].set()
    await blocker
    assert "late" not in run.order


async def test_cancel_before_deadline_while_queued_is_cancelled_before_dispatch(executor):
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor)
    blocker = await _start_blocker(sched, run)
    ticket = JobTicket("final", "s1")
    f = asyncio.create_task(sched.submit_final("x", "s1", deadline=time.monotonic() + 30, ticket=ticket))
    await asyncio.sleep(0.02)
    f.cancel()
    with pytest.raises(asyncio.CancelledError):
        await f
    assert ticket.state == "cancelled_before_dispatch"
    assert sched.stats["finals_cancelled_before_dispatch"] == 1
    run.release["blocker"].set()
    await blocker
    assert "x" not in run.order


async def test_final_timeout_after_dispatch_job_finishes_and_worker_not_reused_early(executor):
    run = Gated(gates=["slow"])
    sched = InferenceScheduler(run, executor)
    ticket = JobTicket("final", "s1")
    deadline = time.monotonic() + 0.1
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sched.submit_final("slow", "s1", deadline=deadline, ticket=ticket), 0.1)
    assert run.wait_started("slow").is_set()
    assert ticket.state == "timed_out_running" and ticket.abandoned
    assert sched.stats["finals_timed_out_running"] == 1
    # The abandoned decode still owns the worker: the next final must not start until it returns.
    nxt = asyncio.create_task(sched.submit_final("next", "s2"))
    await asyncio.sleep(0.1)
    assert "next" not in run.order
    run.release["slow"].set()                      # no thread was killed; it just completes
    assert await nxt == "text:next"
    assert run.order == ["slow", "next"]
    assert ticket.state == "timed_out_running" and ticket.t_end is not None


async def test_no_duplicate_final_dispatch(executor):
    run = Gated()
    sched = InferenceScheduler(run, executor)
    ticket = JobTicket("final", "s1")
    assert await sched.submit_final("once", "s1", ticket=ticket) == "text:once"
    assert ticket.dispatch_count == 1
    with pytest.raises(ValueError):
        await sched.submit_final("once", "s1", ticket=ticket)   # reused ticket is refused
    assert run.order == ["once"]


async def test_each_final_dispatched_exactly_once_under_load(executor):
    run = Gated(sleep_s=0.002)
    sched = InferenceScheduler(run, executor)
    names = [f"f{i}" for i in range(30)] + [f"p{i}" for i in range(30)]
    coros = [sched.submit_final(n, f"s{i % 4}") if n.startswith("f") else sched.submit_partial(n, f"q{i}")
             for i, n in enumerate(names)]
    await asyncio.gather(*coros)
    finals_run = [n for n in run.order if n.startswith("f")]
    assert sorted(finals_run) == sorted(f"f{i}" for i in range(30))
    assert len(finals_run) == len(set(finals_run))


async def test_empty_decode_text_returned_unchanged(executor):
    run = Gated(text=lambda s: "")
    sched = InferenceScheduler(run, executor)
    assert await sched.submit_final("e", "s1") == ""
    assert await sched.submit_partial("e", "s1") == ""     # empty partial is a result, not a skip
    assert sched.stats["finals_completed"] == 1 and sched.stats["partials_executed"] == 1


async def test_engine_error_reaches_caller_and_worker_continues(executor):
    def run(sample):
        if sample == "boom":
            raise RuntimeError("decode failed")
        return "ok"
    sched = InferenceScheduler(run, executor)
    with pytest.raises(RuntimeError):
        await sched.submit_final("boom", "s1")
    assert await sched.submit_final("fine", "s1") == "ok"
    assert sched.stats["finals_failed"] == 1


# ---------------------------------------------------------------- diagnostics
async def test_scheduler_log_written_when_enabled(executor, tmp_path):
    log = tmp_path / "sched.jsonl"
    run = Gated(gates=["blocker"])
    sched = InferenceScheduler(run, executor, log_path=str(log))
    blocker = await _start_blocker(sched, run)
    f = asyncio.create_task(sched.submit_final("f", "s1"))
    await asyncio.sleep(0.02)
    assert await sched.submit_partial("p", "s2") is None
    run.release["blocker"].set()
    await asyncio.gather(blocker, f)
    recs = [json.loads(l) for l in log.read_text().splitlines()]
    kinds = [r["kind"] for r in recs]
    assert kinds.count("job") == 2 and kinds.count("skip") == 1
    job = next(r for r in recs if r["kind"] == "job" and r["queue_wait_s"] is not None and r["state"] == "completed"
               and r["speaker"] == "s1")
    assert job["queue_wait_s"] >= 0 and job["infer_s"] >= 0 and "finals_q" in job and "partials_q" in job


async def test_scheduler_writes_nothing_when_log_disabled(executor, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sched = InferenceScheduler(Gated(), executor)   # no log_path
    await sched.submit_final("f", "s1")
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------- session-level behaviour
class SchedFakeEngine(TranscriptionEngine):
    supports_partial = True
    supports_scheduling = True

    def __init__(self, text="hello world", sleep_s=0.0, gates=()):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.run = Gated(gates=gates, text=lambda s: text, sleep_s=sleep_s)
        self.scheduler = InferenceScheduler(self.run, self.executor, prepare=lambda b: len(b))

    async def transcribe_final(self, pcm_bytes, *, speaker_id=None, deadline=None, ticket=None):
        return await self.scheduler.submit_final(pcm_bytes, speaker_id, deadline, ticket)

    async def transcribe_partial(self, pcm_bytes, *, speaker_id=None):
        text = await self.scheduler.submit_partial(pcm_bytes, speaker_id)
        return None if text is None else text.split()

    async def shutdown(self):
        self.executor.shutdown(wait=False)


def _chunk(v, n=1600):
    import numpy as np
    return np.full(n, v, dtype=np.int16).tobytes()


async def _speak(ws, marker=16000, n_speech=4, n_quiet=5):
    for _ in range(n_speech):
        ws.feed(_chunk(marker))
        await asyncio.sleep(0.005)
    for _ in range(n_quiet):
        ws.feed(_chunk(10))
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)


def _finals(ws):
    return [json.loads(m) for m in ws.sent if json.loads(m).get("partial") is False]


async def test_session_final_sent_with_scheduled_engine_and_message_format_unchanged(tmp_path, monkeypatch):
    diag_file = tmp_path / "diag.jsonl"
    monkeypatch.setenv(flush_diag.ENV_VAR, str(diag_file))
    engine = SchedFakeEngine(text="ask not what your country can do")
    ws = FakeWebSocket()
    task = asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
    await asyncio.sleep(0.02)
    await _speak(ws)
    finals = _finals(ws)
    assert len(finals) == 1
    assert set(finals[0]) == {"type", "text", "partial"} or set(finals[0]) <= {"type", "text", "partial", "ts"}
    assert finals[0]["text"] == "ask not what your country can do" and finals[0]["partial"] is False
    ws.disconnect()
    await task
    recs = [json.loads(l) for l in diag_file.read_text().splitlines()]
    sent = [r for r in recs if r["outcome"] == "final_sent"]
    assert sent and sent[0]["sched_state"] == "completed" and sent[0]["queue_wait_s"] is not None
    await engine.shutdown()


async def test_session_empty_decode_unchanged_not_counted_as_scheduling_failure(tmp_path, monkeypatch):
    diag_file = tmp_path / "diag.jsonl"
    monkeypatch.setenv(flush_diag.ENV_VAR, str(diag_file))
    engine = SchedFakeEngine(text="")
    ws = FakeWebSocket()
    task = asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
    await asyncio.sleep(0.02)
    await _speak(ws)
    assert _finals(ws) == []                      # still silently dropped, exactly like before
    ws.disconnect()
    await task
    outcomes = [json.loads(l)["outcome"] for l in diag_file.read_text().splitlines()]
    assert "dropped_empty_text" in outcomes
    assert not any(o in outcomes for o in ("dropped_timeout", "dropped_expired_in_queue", "dropped_timeout_running"))
    await engine.shutdown()


async def test_session_final_timeout_while_running_reports_timeout_running(tmp_path, monkeypatch):
    import core.speaker_session as ss
    monkeypatch.setattr(ss, "FINAL_FLUSH_TIMEOUT_SECONDS", 0.2)
    diag_file = tmp_path / "diag.jsonl"
    monkeypatch.setenv(flush_diag.ENV_VAR, str(diag_file))
    engine = SchedFakeEngine()
    engine.run.block_set = True                      # every decode blocks until released
    ws = FakeWebSocket()
    task = asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
    await asyncio.sleep(0.02)
    await _speak(ws)
    await asyncio.sleep(0.4)
    ws.disconnect()
    engine.run.block_all.set()
    await task
    recs = [json.loads(l) for l in diag_file.read_text().splitlines()]
    assert any(r["outcome"] == "dropped_timeout_running" and r["sched_abandoned"] for r in recs), recs
    await engine.shutdown()


async def test_session_final_expired_in_queue_reports_and_never_decodes(tmp_path, monkeypatch):
    import core.speaker_session as ss
    monkeypatch.setattr(ss, "FINAL_FLUSH_TIMEOUT_SECONDS", 0.2)
    diag_file = tmp_path / "diag.jsonl"
    monkeypatch.setenv(flush_diag.ENV_VAR, str(diag_file))
    engine = SchedFakeEngine()
    engine.run.block_set = True
    blocker = asyncio.create_task(engine.scheduler.submit_final(b"blocker", "x"))   # hogs the worker
    await _until(lambda: len(engine.run.order) == 1)
    ws = FakeWebSocket()
    task = asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
    await asyncio.sleep(0.02)
    await _speak(ws)
    await asyncio.sleep(0.4)
    assert _finals(ws) == []
    engine.run.block_all.set()
    await blocker
    ws.disconnect()
    await task
    recs = [json.loads(l) for l in diag_file.read_text().splitlines()]
    assert any(r["outcome"] == "dropped_expired_in_queue" for r in recs), recs
    assert engine.run.order == [len(b"blocker")], "expired final must not have been decoded"
    await engine.shutdown()


async def test_session_diagnostics_disabled_has_no_effect_on_behaviour(tmp_path, monkeypatch):
    monkeypatch.delenv(flush_diag.ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    engine = SchedFakeEngine(text="plain")
    ws = FakeWebSocket()
    task = asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
    await asyncio.sleep(0.02)
    await _speak(ws)
    assert [f["text"] for f in _finals(ws)] == ["plain"]
    ws.disconnect()
    await task
    assert list(tmp_path.iterdir()) == []
    await engine.shutdown()


async def test_session_multiple_concurrent_speakers_all_finals_delivered():
    engine = SchedFakeEngine(text="spoken words here", sleep_s=0.01)
    sockets = [FakeWebSocket() for _ in range(4)]
    tasks = [asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
             for ws in sockets]
    await asyncio.sleep(0.02)
    await asyncio.gather(*[_speak(ws) for ws in sockets])
    await asyncio.sleep(0.3)
    for ws in sockets:
        assert [f["text"] for f in _finals(ws)] == ["spoken words here"]     # exactly one each: no dupes, none missing
        ws.disconnect()
    await asyncio.gather(*tasks)
    assert engine.scheduler.stats["finals_completed"] == 4
    await engine.shutdown()


async def test_session_skipped_partial_does_not_send_or_crash():
    """transcribe_partial returning None (backpressure skip) is not an empty result and sends nothing."""
    class SkipAll(SchedFakeEngine):
        async def transcribe_partial(self, pcm_bytes, *, speaker_id=None):
            return None
    engine = SkipAll(text="done")
    ws = FakeWebSocket()
    task = asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
    await asyncio.sleep(0.02)
    for _ in range(4):
        ws.feed(_chunk(16000)); await asyncio.sleep(0.2)     # long enough for several partial cycles
    ws.feed(_chunk(10)); ws.feed(_chunk(10)); ws.feed(_chunk(10)); ws.feed(_chunk(10)); ws.feed(_chunk(10))
    await asyncio.sleep(0.1)
    assert not [json.loads(m) for m in ws.sent if json.loads(m).get("partial") is True]
    assert [f["text"] for f in _finals(ws)] == ["done"]
    ws.disconnect()
    await task
    await engine.shutdown()


async def test_legacy_engine_without_scheduling_still_works_with_session():
    engine = FakeEngine(final_text="legacy")
    ws = FakeWebSocket()
    task = asyncio.create_task(run_speaker_session(ws, None, engine, _buf(), SessionRegistry()))
    await asyncio.sleep(0.02)
    await _speak(ws)
    assert [f["text"] for f in _finals(ws)] == ["legacy"]
    ws.disconnect()
    await task
