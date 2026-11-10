"""Second-pass text refinement of finalized EOU utterances (staging).

The live path (EOU model -> partial/final messages) is never touched or awaited. After a final has been sent, the
utterance's audio is replayed through a *separate* Nemotron streaming worker process; if its text is a sane improvement
the stored transcript line is replaced and a `refine` message is broadcast so clients swap the line in place.

Safety rules: the live final is always kept unless the refinement arrives in time and passes `accept()`; a bounded number
of jobs is queued and extra jobs are dropped (never delayed behind the live path); every failure leaves the EOU text.
Nemotron here is an ASR model (audio in, text out) -- it re-listens to the utterance, it does not rewrite text.
"""
import asyncio
import difflib
import json
import logging
import re
import time

from .config import SAMPLE_RATE
from .numbers import to_digits

logger = logging.getLogger(__name__)

MIN_UTTERANCE_SECONDS = 0.5
CHUNK_BYTES = SAMPLE_RATE * 2  # 1 s of PCM16 per websocket message
_WORD = re.compile(r"[a-z0-9']+")
_FILLERS = {"uh", "um", "uhm", "er", "erm", "ah", "hmm", "mm"}
MAX_LEN_DRIFT = 0.25      # refined may be at most 25% longer/shorter (in words) than the live text
MIN_SIMILARITY = 0.8      # word-level similarity of the two texts
MIN_WORDS_TO_CHANGE_WORDS = 4  # shorter utterances may only change case, punctuation, digits and fillers


def _words(text: str) -> list[str]:
    """Comparison form: digits instead of spoken numbers, lowercase, no punctuation, no filler words."""
    return [w for w in _WORD.findall(to_digits(text).lower()) if w not in _FILLERS]


def refine_text(original: str, refined: str) -> str | None:
    """The text to show instead of `original`, or None to keep the live text.

    Numbers are written as digits. The refinement is applied only if it is a plausible re-transcription:
    - same words once case, punctuation, fillers and number format are ignored (pure formatting fix), or
    - for utterances of 4+ words: word count within 25% and word-level similarity of at least 0.8.
    A result that is empty, identical to the live text, a different sentence, or a short utterance with changed words
    is rejected."""
    final = to_digits((refined or "").strip())
    if not final or final == original.strip():
        return None
    a, b = _words(original), _words(final)
    if not a or not b:
        return None
    if a == b:
        return final
    if len(a) < MIN_WORDS_TO_CHANGE_WORDS:
        return None
    if not (1 - MAX_LEN_DRIFT) <= len(b) / len(a) <= 1 / (1 - MAX_LEN_DRIFT):
        return None
    if difflib.SequenceMatcher(None, a, b).ratio() < MIN_SIMILARITY:
        return None
    return final


def accept(original: str, refined: str) -> bool:
    return refine_text(original, refined) is not None


class Refiner:
    def __init__(self, engine, max_pending: int = 6, concurrency: int = 1, timeout: float = 20.0, log_path: str | None = None):
        self.engine = engine
        self.max_pending = max_pending
        self.timeout = timeout
        self.log_path = log_path
        self._sem = asyncio.Semaphore(concurrency)
        self._pending = 0
        self._tasks: set[asyncio.Task] = set()
        self.stats = {"submitted": 0, "applied": 0, "unchanged": 0, "rejected": 0, "dropped": 0, "failed": 0}

    def submit(self, pcm: bytes, original: str, on_refined) -> bool:
        """Queue a job and return at once. `on_refined(refined_text)` is awaited only when the result is accepted."""
        if len(pcm) < MIN_UTTERANCE_SECONDS * SAMPLE_RATE * 2:
            return False
        if self._pending >= self.max_pending:
            self.stats["dropped"] += 1
            return False
        self._pending += 1
        self.stats["submitted"] += 1
        task = asyncio.create_task(self._run(pcm, original, on_refined))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _recognize(self, pcm: bytes) -> str:
        stream = await self.engine.open_stream()
        try:
            for i in range(0, len(pcm), CHUNK_BYTES):
                await stream.send_audio(pcm[i:i + CHUNK_BYTES])
            await stream.flush()
            async for ev in stream.events():
                if ev.get("type") == "final":
                    return (ev.get("text") or "").strip()
                if ev.get("type") == "error":
                    raise RuntimeError(ev.get("detail"))
            return ""
        finally:
            await stream.close()

    async def _run(self, pcm: bytes, original: str, on_refined):
        t0 = time.monotonic()
        try:
            async with self._sem:
                refined = await asyncio.wait_for(self._recognize(pcm), self.timeout)
            final = refine_text(original, refined)
            self._log(original, refined, final, time.monotonic() - t0, len(pcm) / (SAMPLE_RATE * 2))
            if final is not None:
                await on_refined(final)
                self.stats["applied"] += 1
            elif to_digits(refined.strip()) == original.strip():
                self.stats["unchanged"] += 1
            else:
                self.stats["rejected"] += 1
        except Exception as e:  # any failure keeps the live EOU text
            self.stats["failed"] += 1
            logger.warning("refinement skipped: %s", type(e).__name__)
        finally:
            self._pending -= 1

    def _log(self, original, refined, final, took, audio_s):
        if not self.log_path:
            return
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": round(time.time(), 3), "audio_s": round(audio_s, 2), "took_s": round(took, 3),
                                    "accepted": final is not None, "eou": original, "nemotron": refined,
                                    "shown": final}) + "\n")
        except OSError:
            pass
