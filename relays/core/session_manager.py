"""Session/broadcast lifecycle shared by all three relays: a speaker
connects with ?role=speaker&session=<token>, a viewer connects with
?role=viewer&session=<token> and receives the same transcript messages
read-only. The session ends the moment the speaker disconnects.
"""
import json
import logging

import websockets

from .protocol import ended_message

logger = logging.getLogger(__name__)


class SessionRegistry:
    """One instance per relay process. Tracks which session_ids have
    viewers (`sessions`) and which have a currently-connected speaker
    (`active_speakers`) -- the latter is what lets viewer cleanup tell
    "no speaker ever showed up for this id" (safe to drop the empty
    entry) apart from "speaker is live with zero viewers right now"
    (must not drop it).
    """

    def __init__(self):
        self.sessions: dict[str, set] = {}
        self.active_speakers: set[str] = set()

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

    async def handle_viewer(self, websocket, session_id: str | None):
        if not session_id:
            await websocket.close(code=4400, reason="missing session id")
            return
        viewers = self.sessions.setdefault(session_id, set())
        viewers.add(websocket)
        logger.info(f"Viewer joined session {session_id}")
        try:
            async for _ in websocket:
                pass  # viewers don't send anything; just hold the connection open
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            viewers.discard(websocket)
            if not viewers and session_id not in self.active_speakers:
                self.sessions.pop(session_id, None)
            logger.info(f"Viewer left session {session_id}")

    def speaker_connected(self, session_id: str | None):
        if session_id:
            self.active_speakers.add(session_id)

    async def speaker_disconnected(self, session_id: str | None):
        if not session_id:
            return
        self.active_speakers.discard(session_id)
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
