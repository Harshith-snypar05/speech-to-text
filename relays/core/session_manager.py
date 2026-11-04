"""Session/broadcast lifecycle shared by all three relays: a speaker
connects with ?role=speaker&session=<token>, a viewer connects with
?role=viewer&session=<token> and receives the same transcript messages
read-only. Live broadcast ends the moment the speaker disconnects, but
the transcript itself (see transcript_store) outlives that -- a viewer
opening the link later, during or after the session, still gets it.
"""
import json
import logging

import websockets

from . import transcript_store
from .protocol import ended_message, final_message, is_valid_session_id

logger = logging.getLogger(__name__)

# Close codes in the 4000-4999 private-use range (the websockets library
# and browsers treat these as ordinary application closes, not protocol
# errors) so the client can tell these apart if it ever wants to.
CLOSE_INVALID_SESSION = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_AT_CAPACITY = 4429


class SessionRegistry:
    """One instance per relay process. Tracks which session_ids have
    viewers (`sessions`), which have a currently-connected speaker
    (`active_speakers`) -- the latter is what lets viewer cleanup tell
    "no speaker ever showed up for this id" (safe to drop the empty
    entry) apart from "speaker is live with zero viewers right now"
    (must not drop it) -- and an optional per-session access code set by
    whoever is currently speaking.
    """

    def __init__(self, max_viewers_per_session: int = 50, max_total_connections: int = 200):
        self.sessions: dict[str, set] = {}
        self.active_speakers: set[str] = set()
        self.access_codes: dict[str, str] = {}
        self.max_viewers_per_session = max_viewers_per_session
        self.max_total_connections = max_total_connections
        self._total_connections = 0

    async def broadcast(self, session_id: str, payload: dict):
        viewers = self.sessions.get(session_id)
        if not viewers:
            return
        dead = []
        message = json.dumps(payload)
        for viewer in viewers:
            try:
                await viewer.send(message)
            except Exception:
                dead.append(viewer)
        for viewer in dead:
            viewers.discard(viewer)

    async def handle_viewer(self, websocket, session_id: str | None, access_code: str | None = None):
        if not is_valid_session_id(session_id):
            await websocket.close(code=CLOSE_INVALID_SESSION, reason="missing or malformed session id")
            return
        persisted = transcript_store.get_session(session_id)
        # The in-memory code (live session) wins if present; otherwise fall
        # back to the persisted one so a code-protected session still
        # requires it after the speaker has disconnected.
        required_code = self.access_codes.get(session_id) or (persisted["access_code"] if persisted else None)
        if required_code and access_code != required_code:
            await websocket.close(code=CLOSE_UNAUTHORIZED, reason="invalid or missing access code")
            return
        if self._total_connections >= self.max_total_connections:
            await websocket.close(code=CLOSE_AT_CAPACITY, reason="server at capacity")
            return

        history = transcript_store.get_history(session_id) if persisted else []
        try:
            for text in history:
                await websocket.send(json.dumps(final_message(text)))
        except websockets.exceptions.ConnectionClosed:
            return

        already_ended = persisted is not None and persisted["ended_at"] is not None and session_id not in self.active_speakers
        if already_ended:
            try:
                await websocket.send(json.dumps(ended_message()))
            except websockets.exceptions.ConnectionClosed:
                pass
            await websocket.close(code=1000, reason="session ended")
            logger.info(f"Viewer opened ended session {session_id}, replayed {len(history)} saved message(s)")
            return

        viewers = self.sessions.setdefault(session_id, set())
        if len(viewers) >= self.max_viewers_per_session:
            await websocket.close(code=CLOSE_AT_CAPACITY, reason="session viewer limit reached")
            return
        viewers.add(websocket)
        self._total_connections += 1
        logger.info(f"Viewer joined session {session_id} ({len(viewers)}/{self.max_viewers_per_session})")
        try:
            async for _ in websocket:
                pass  # viewers don't send anything; just hold the connection open
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            viewers.discard(websocket)
            self._total_connections -= 1
            if not viewers and session_id not in self.active_speakers:
                self.sessions.pop(session_id, None)
                self.access_codes.pop(session_id, None)
            logger.info(f"Viewer left session {session_id}")

    def speaker_connected(self, session_id: str | None, access_code: str | None = None):
        if session_id:
            self.active_speakers.add(session_id)
            if access_code:
                self.access_codes[session_id] = access_code
            else:
                self.access_codes.pop(session_id, None)
            transcript_store.start_session(session_id, access_code)

    async def speaker_disconnected(self, session_id: str | None):
        if not session_id:
            return
        self.active_speakers.discard(session_id)
        self.access_codes.pop(session_id, None)
        transcript_store.end_session(session_id)
        await self.broadcast(session_id, ended_message())
        # list(...) snapshots the set -- closing each viewer triggers their
        # own handler's finally block, which discards them from this same
        # set concurrently; iterating the live set directly raises
        # "Set changed size during iteration".
        for viewer in list(self.sessions.pop(session_id, ())):
            try:
                await viewer.close(code=1000, reason="session ended")
            except Exception:
                pass
