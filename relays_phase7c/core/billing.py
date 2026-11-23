"""Customer-account metering for the speech relay. Enabled only when SCRIPTLIV_API_URL is set.

The relay never decides who may speak or how much they have left; the ScriptLiv API does. This module only
  1. asks the API to validate the speaker's token and check their quota when they connect,
  2. reports the speaker's cumulative audio seconds every REPORT_EVERY_SECONDS and once more when they leave,
  3. tells the speaker loop to stop when the API says the account has no minutes left, or no longer exists.
Viewers never touch this module, so viewers are never billed. The reports are cumulative, so a retry can't double-bill.
The shared secret comes from SCRIPTLIV_RELAY_SECRET (environment only, never logged).
"""
import asyncio
import json
import logging
import math
import os
import time
import urllib.request

logger = logging.getLogger(__name__)

API_URL = os.environ.get("SCRIPTLIV_API_URL", "").rstrip("/")
REPORT_EVERY_SECONDS = float(os.environ.get("SCRIPTLIV_REPORT_EVERY_SECONDS", "10"))
TIMEOUT = 6.0
FINAL_ATTEMPTS = 3
FINAL_RETRY_DELAY = 1.0
# If the API cannot be reached for this long while a session runs, the session is stopped instead of continuing
# unverified (fail closed). It counts from the first FAILED report, so a healthy API, a quiet speaker or sparse audio
# never trips it.
UNVERIFIED_GRACE_SECONDS = float(os.environ.get("SCRIPTLIV_UNVERIFIED_GRACE_SECONDS", "60"))
# Denial reasons meaning "this account/session may no longer be served", as opposed to "out of minutes".
ACCOUNT_GONE_REASONS = ("account_unavailable", "invalid_token")
NOT_ALLOWED_REASONS = ACCOUNT_GONE_REASONS + ("billing_unavailable",)


def _now() -> float:
    return time.monotonic()


def close_params(billing) -> tuple:
    """(websocket close code, reason) for a session the billing context has stopped. 4401 (not allowed) for a deleted or
    unverifiable account, 4402 for quota or session-cap exhaustion."""
    reason = getattr(billing, "deny_reason", None)
    if reason in NOT_ALLOWED_REASONS:
        return 4401, reason
    return 4402, "session_limit" if billing is not None and billing.hit_session_cap else "out_of_minutes"


def enabled() -> bool:
    return bool(API_URL and os.environ.get("SCRIPTLIV_RELAY_SECRET"))


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(API_URL + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Relay-Secret": os.environ["SCRIPTLIV_RELAY_SECRET"]})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


async def authorize_start(token: str, session_id: str) -> dict:
    """{'allowed': bool, 'reason': str|None, 'user_id': str, 'remaining_seconds': int}. Fails closed if the API is down."""
    try:
        return await asyncio.to_thread(_post, "/internal/v1/sessions/start", {"token": token or "", "session_id": session_id})
    except Exception as e:
        logger.warning("billing authorize failed: %s", type(e).__name__)
        return {"allowed": False, "reason": "billing_unavailable", "remaining_seconds": 0}


class BillingContext:
    """Strict allowance for one speaker connection.

    The allowance is a hard ceiling on cumulative audio seconds: `take()` is called with every audio chunk BEFORE it is
    sent to the engine and returns how much of it fits. Anything past the ceiling is never processed or billed."""

    def __init__(self, user_id: str, session_id: str, remaining_seconds: int, base_seconds: float = 0.0, session_cap_seconds: float | None = None):
        self.user_id = user_id
        self.session_id = session_id
        # a reconnect to the same session carries on from what the API already billed, so seconds are neither
        # lost nor billed twice
        self.audio_seconds = float(base_seconds)
        self._reported_at = float(base_seconds)
        self._remaining = base_seconds + remaining_seconds   # ceiling on cumulative audio seconds
        self._inflight = None
        self.session_cap = session_cap_seconds   # per-session ceiling of the plan (free tier), None when uncapped
        self.deny_reason = None
        self.exhausted = False
        self.dropped_seconds = 0.0   # audio that arrived past the ceiling and was discarded unprocessed
        self._failing_since = None   # monotonic time of the first report failure not yet followed by a success

    @property
    def hit_session_cap(self) -> bool:
        """True when this session stopped because of the plan's per-session cap, not because the account ran dry."""
        if self.deny_reason == "session_limit":
            return True
        return self.session_cap is not None and self.deny_reason is None and self.audio_seconds >= self.session_cap - 0.01

    def room(self) -> float:
        return max(0.0, self._remaining - self.audio_seconds)

    def take(self, n_samples: int, sample_rate: int) -> int:
        """How many of `n_samples` may be processed. Advances the meter by exactly that much; sets `exhausted` once
        the ceiling is reached (also when a chunk ends exactly on it)."""
        self._check_account()
        fit = min(n_samples, max(0, int(math.floor(self.room() * sample_rate + 1e-6))))
        self.audio_seconds += fit / sample_rate
        if fit < n_samples:
            self.dropped_seconds += (n_samples - fit) / sample_rate
            self.audio_seconds = self._remaining   # sub-sample remainder: snap to the ceiling, never past it
        if self.room() <= 0:
            self.exhausted = True
        elif self.audio_seconds - self._reported_at >= REPORT_EVERY_SECONDS and (self._inflight is None or self._inflight.done()):
            self._inflight = asyncio.create_task(self._report(False))
        return fit

    def _stop(self, reason: str) -> None:
        """Stop serving this session now: nothing past the audio already taken is processed."""
        self.deny_reason = reason
        self._remaining = min(self._remaining, self.audio_seconds)
        self.exhausted = True

    def _check_account(self) -> None:
        """Cheap in-memory checks on every chunk (no I/O): the mirror or an earlier report found the account gone, or the
        API has been unreachable for too long to keep serving unverified."""
        if self.exhausted:
            return
        from . import transcript_store
        if transcript_store.is_blocked(self.session_id):
            self._stop("account_unavailable")
        elif self._failing_since is not None and _now() - self._failing_since > UNVERIFIED_GRACE_SECONDS:
            logger.error("usage reports failing for over %.0fs; stopping session %s (fail closed)", UNVERIFIED_GRACE_SECONDS, self.session_id)
            self._stop("billing_unavailable")

    def _account_gone(self) -> None:
        from . import transcript_store
        transcript_store.block_session(self.session_id)   # purge local rows, refuse every later write for this session

    async def _report(self, final: bool) -> bool:
        at = self.audio_seconds
        try:
            r = await asyncio.to_thread(_post, "/internal/v1/usage", {"user_id": self.user_id, "session_id": self.session_id,
                                                                       "cumulative_seconds": at, "final": final})
            self._reported_at = at
            self._failing_since = None
            if not r.get("allowed", True) and r.get("reason") in ACCOUNT_GONE_REASONS:
                # the account is deleting or gone (also on the final report): stop every write for this session
                self._account_gone()
                self._stop(r.get("reason"))
            elif not final:
                if r.get("session_cap_seconds") is not None:
                    self.session_cap = float(r["session_cap_seconds"])
                if not r.get("allowed", True):
                    self.deny_reason = r.get("reason")
                    self._remaining = min(self._remaining, at)
                    self.exhausted = True
                else:
                    # re-anchor to what the server has billed (not to `at`, which can be a fraction ahead of it);
                    # the server never grants past what the account had when the session started
                    base = r.get("base_seconds")
                    if base is not None:
                        self._remaining = float(base) + r.get("remaining_seconds", 0)
            return True
        except Exception as e:  # keep serving for now; the next report carries the full cumulative total
            logger.warning("usage report failed: %s", type(e).__name__)
            if self._failing_since is None:
                self._failing_since = _now()   # take() stops the session once this exceeds the grace period
            return False

    async def finish(self):
        if self._inflight is not None:
            try:
                await self._inflight
            except Exception:
                pass
        # the closing report is the last chance to bill the tail of the session: retry it (it is cumulative, so a
        # retry can never bill twice)
        for attempt in range(FINAL_ATTEMPTS):
            if await self._report(True):
                return
            await asyncio.sleep(FINAL_RETRY_DELAY * (attempt + 1))
        logger.error("final usage report for %s not delivered", self.session_id)
