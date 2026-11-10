"""Phase 7C inference scheduler: finals-first priority, partial backpressure,
deadline-aware final dispatch and explicit accounting.

Replaces the engine's FIFO asyncio.Lock. All inference still runs on the ONE
dedicated executor thread (same native-call thread affinity as before); this
module only decides which waiting request goes next.

Rules
-----
* Finals are dispatched before any waiting partial. Finals keep FIFO order
  among themselves, which preserves per-speaker final order.
* A job already running on the executor thread is never preempted, and its
  thread is never terminated. Cancelling the awaiting coroutine only detaches
  the caller; the dispatcher still waits for the executor call to return
  before it starts anything else, and records that job as abandoned.
* A final carries an absolute deadline (monotonic clock) taken from the
  original flush request. Queue wait counts against it. A final whose
  deadline has passed is never started.
* A partial is skipped (None returned, nothing queued) when the same speaker
  already has a partial queued or running, or when any final is waiting.
  At most one partial per speaker is ever queued, so the partial backlog is
  bounded by the number of speakers. A queued partial is dropped when a final
  for the same speaker arrives (it would be stale anyway) and when it has
  waited longer than partial_max_queue_age.
* Every job ends in exactly one state; counters and an optional JSONL log
  record it. Text, including an empty string, is returned untouched.
"""
import asyncio
import json
import threading
import time
from collections import OrderedDict, deque


class FinalExpired(Exception):
    """A final's deadline passed before it was dispatched; it was never run."""


class JobTicket:
    """Observable per-job record. The caller may pass one in to read the
    outcome after the call ends (including after a timeout cancel)."""

    __slots__ = ("kind", "speaker_id", "state", "t_enq", "t_start", "t_end", "deadline",
                 "dispatch_count", "reason", "abandoned")

    def __init__(self, kind: str, speaker_id=None):
        self.kind = kind
        self.speaker_id = speaker_id
        self.state = "new"   # queued | running | completed | failed | expired_in_queue |
        #                      cancelled_before_dispatch | timed_out_running | cancelled_running | skipped
        self.t_enq = None
        self.t_start = None
        self.t_end = None
        self.deadline = None
        self.dispatch_count = 0
        self.reason = None
        self.abandoned = False

    @property
    def queue_wait_s(self):
        if self.t_enq is None:
            return None
        end = self.t_start if self.t_start is not None else self.t_end
        return None if end is None else end - self.t_enq

    @property
    def infer_s(self):
        return None if self.t_start is None or self.t_end is None else self.t_end - self.t_start


class _Job:
    __slots__ = ("ticket", "samples", "fut", "enq_depth", "key")

    def __init__(self, ticket, samples, fut, enq_depth, key=None):
        self.key = key   # partial bookkeeping key: speaker id, or a unique token for anonymous callers
        self.ticket = ticket
        self.samples = samples
        self.fut = fut
        self.enq_depth = enq_depth


_CANCEL_TOLERANCE_S = 0.005


class InferenceScheduler:
    def __init__(self, run_sync, executor, prepare=None, *, partial_max_queue_age=2.0,
                 clock=time.monotonic, log_path=None):
        self._run_sync = run_sync
        self._executor = executor
        self._prepare = prepare or (lambda x: x)
        self._max_age = partial_max_queue_age
        self._clock = clock
        self._log_path = log_path or None
        self._log_lock = threading.Lock()
        self._finals: deque = deque()
        self._partials: OrderedDict = OrderedDict()   # speaker_id -> _Job (queued)
        self._partial_inflight: set = set()            # queued OR running partials, by speaker
        self._running: _Job | None = None
        self._wakeup = asyncio.Event()
        self._dispatcher: asyncio.Task | None = None
        self.stats = {
            "finals_requested": 0, "finals_dispatched": 0, "finals_completed": 0, "finals_failed": 0,
            "finals_expired_in_queue": 0, "finals_cancelled_before_dispatch": 0,
            "finals_timed_out_running": 0, "finals_cancelled_running": 0,
            "partials_requested": 0, "partials_executed": 0, "partials_failed": 0,
            "partials_skipped": 0, "partials_skipped_by_reason": {},
            "partials_abandoned_running": 0,
        }

    # ------------------------------------------------------------------ logging
    def _log(self, rec: dict) -> None:
        if not self._log_path:
            return
        try:
            with self._log_lock, open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception:
            pass  # diagnostics must never affect scheduling

    def _depth(self) -> dict:
        return {"finals_q": len(self._finals), "partials_q": len(self._partials),
                "running": self._running.ticket.kind if self._running else None}

    # --------------------------------------------------------------- bookkeeping
    def _count_skip(self, reason: str, speaker_id) -> None:
        self.stats["partials_skipped"] += 1
        by = self.stats["partials_skipped_by_reason"]
        by[reason] = by.get(reason, 0) + 1
        if self._log_path:
            self._log({"kind": "skip", "t": self._clock(), "speaker": speaker_id, "reason": reason, **self._depth()})

    def partial_skip_reason(self, speaker_id):
        if speaker_id is not None and speaker_id in self._partial_inflight:
            return "same_speaker_pending"
        if self._finals:
            return "final_waiting"
        return None

    def _ensure_dispatcher(self) -> None:
        loop = asyncio.get_running_loop()
        if getattr(self, "_loop", None) is not loop:   # new event loop (e.g. per-test loops): rebind
            self._loop = loop
            self._wakeup = asyncio.Event()
            self._dispatcher = None
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = asyncio.get_running_loop().create_task(self._dispatch_loop())
        self._wakeup.set()

    def _job_record(self, job: _Job) -> None:
        if not self._log_path:
            return
        t = job.ticket
        self._log({"kind": "job", "type": t.kind, "speaker": t.speaker_id, "state": t.state, "reason": t.reason,
                   "t_enq": t.t_enq, "t_start": t.t_start, "t_end": t.t_end, "deadline": t.deadline,
                   "n_samples": len(job.samples), "queue_wait_s": t.queue_wait_s, "infer_s": t.infer_s,
                   "abandoned": t.abandoned, "dispatch_count": t.dispatch_count, **job.enq_depth})

    # ------------------------------------------------------------------- submit
    async def submit_final(self, pcm, speaker_id=None, deadline=None, ticket: JobTicket | None = None) -> str:
        ticket = ticket if ticket is not None else JobTicket("final", speaker_id)
        if ticket.state != "new":
            raise ValueError(f"final ticket already used (state={ticket.state}); refusing duplicate dispatch")
        now = self._clock()
        ticket.kind, ticket.speaker_id, ticket.t_enq, ticket.deadline = "final", speaker_id, now, deadline
        self.stats["finals_requested"] += 1
        samples = self._prepare(pcm)
        job = _Job(ticket, samples, asyncio.get_running_loop().create_future(), self._depth())
        if deadline is not None and now >= deadline:
            ticket.state, ticket.t_end = "expired_in_queue", now
            self.stats["finals_expired_in_queue"] += 1
            self._job_record(job)
            raise FinalExpired("final deadline already passed at submit")
        ticket.state = "queued"
        # A partial still queued for this speaker is obsolete the moment its final arrives.
        old = self._partials.pop(speaker_id, None) if speaker_id is not None else None
        if old is not None:
            self._end_skipped_partial(old, "superseded_by_final")
        self._finals.append(job)
        self._ensure_dispatcher()
        try:
            return await job.fut
        except asyncio.CancelledError:
            self._on_final_cancelled(job)
            raise

    async def submit_partial(self, pcm, speaker_id=None):
        """Returns decoded text, or None when the request was skipped/dropped."""
        self.stats["partials_requested"] += 1
        reason = self.partial_skip_reason(speaker_id)
        if reason:
            self._count_skip(reason, speaker_id)
            return None
        ticket = JobTicket("partial", speaker_id)
        ticket.t_enq = self._clock()
        ticket.state = "queued"
        key = speaker_id if speaker_id is not None else object()
        job = _Job(ticket, self._prepare(pcm), asyncio.get_running_loop().create_future(), self._depth(), key)
        self._partials[key] = job
        self._partial_inflight.add(key)
        self._ensure_dispatcher()
        try:
            return await job.fut
        except asyncio.CancelledError:
            self._on_partial_cancelled(job)
            raise

    # ------------------------------------------------------------ cancel handling
    def _on_final_cancelled(self, job: _Job) -> None:
        t = job.ticket
        now = self._clock()
        late = t.deadline is not None and now + _CANCEL_TOLERANCE_S >= t.deadline
        if t.state == "queued":
            try:
                self._finals.remove(job)
            except ValueError:
                pass
            t.t_end = now
            if late:
                t.state = "expired_in_queue"
                self.stats["finals_expired_in_queue"] += 1
            else:
                t.state = "cancelled_before_dispatch"
                self.stats["finals_cancelled_before_dispatch"] += 1
            self._job_record(job)
        elif t.state == "running":
            t.abandoned = True   # executor call keeps going; dispatcher finishes the bookkeeping
            if late:
                t.state = "timed_out_running"
                self.stats["finals_timed_out_running"] += 1
            else:
                t.state = "cancelled_running"
                self.stats["finals_cancelled_running"] += 1

    def _on_partial_cancelled(self, job: _Job) -> None:
        t = job.ticket
        if t.state == "queued":
            if self._partials.get(job.key) is job:
                del self._partials[job.key]
            self._partial_inflight.discard(job.key)
            t.state, t.t_end, t.reason = "cancelled_before_dispatch", self._clock(), "cancelled"
            self._job_record(job)
        elif t.state == "running":
            t.abandoned = True
            self.stats["partials_abandoned_running"] += 1

    def _end_skipped_partial(self, job: _Job, reason: str) -> None:
        t = job.ticket
        t.state, t.reason, t.t_end = "skipped", reason, self._clock()
        self._partial_inflight.discard(job.key)
        self._count_skip(reason, t.speaker_id)
        self._job_record(job)
        if not job.fut.done():
            job.fut.set_result(None)

    # ----------------------------------------------------------------- dispatcher
    def _next_job(self):
        now = self._clock()
        while self._finals:
            job = self._finals.popleft()
            t = job.ticket
            if job.fut.done():
                continue
            if t.deadline is not None and now >= t.deadline:
                t.state, t.t_end = "expired_in_queue", now
                self.stats["finals_expired_in_queue"] += 1
                self._job_record(job)
                job.fut.set_exception(FinalExpired("final deadline passed while queued; not started"))
                continue
            return job
        while self._partials:
            _, job = self._partials.popitem(last=False)
            if job.fut.done():
                self._partial_inflight.discard(job.key)
                continue
            if now - job.ticket.t_enq > self._max_age:
                self._end_skipped_partial(job, "stale_in_queue")
                continue
            return job
        return None

    async def _dispatch_loop(self):
        loop = asyncio.get_running_loop()
        while True:
            job = self._next_job()
            if job is None:
                self._wakeup.clear()
                await self._wakeup.wait()
                continue
            t = job.ticket
            t.state, t.t_start = "running", self._clock()
            t.dispatch_count += 1
            assert t.dispatch_count == 1, "job dispatched twice"
            self._running = job
            if t.kind == "final":
                self.stats["finals_dispatched"] += 1
            err = result = None
            try:
                result = await loop.run_in_executor(self._executor, self._run_sync, job.samples)
            except Exception as e:   # engine error: surfaced to the caller if it is still waiting
                err = e
            t.t_end = self._clock()
            self._running = None
            abandoned = job.fut.done()
            if t.kind == "partial":
                self._partial_inflight.discard(job.key)
            if err is not None:
                key = "finals_failed" if t.kind == "final" else "partials_failed"
                self.stats[key] += 1
                if not abandoned:
                    t.state = "failed"
                    job.fut.set_exception(err)
            elif abandoned:
                if t.state == "running":
                    t.state = "cancelled_running"   # partial whose caller went away mid-decode
            else:
                t.state = "completed"
                self.stats["finals_completed" if t.kind == "final" else "partials_executed"] += 1
                job.fut.set_result(result)
            self._job_record(job)
