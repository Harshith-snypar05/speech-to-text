import asyncio

import pytest

from core.session_manager import CLOSE_AT_CAPACITY, CLOSE_INVALID_SESSION, CLOSE_UNAUTHORIZED, SessionRegistry

from .conftest import FakeWebSocket


async def test_viewer_with_missing_session_id_rejected():
    reg = SessionRegistry()
    ws = FakeWebSocket()
    await reg.handle_viewer(ws, None)
    assert ws.close_code == CLOSE_INVALID_SESSION


async def test_viewer_with_malformed_session_id_rejected():
    reg = SessionRegistry()
    ws = FakeWebSocket()
    await reg.handle_viewer(ws, "x")  # too short
    assert ws.close_code == CLOSE_INVALID_SESSION


async def test_orphaned_session_cleaned_up_after_viewer_leaves():
    reg = SessionRegistry()
    ws = FakeWebSocket()
    task = asyncio.create_task(reg.handle_viewer(ws, "orphan-session"))
    await asyncio.sleep(0.02)
    assert "orphan-session" in reg.sessions
    ws.disconnect()
    await task
    assert "orphan-session" not in reg.sessions


async def test_session_with_active_speaker_survives_zero_viewers():
    reg = SessionRegistry()
    reg.speaker_connected("live-session")
    ws = FakeWebSocket()
    task = asyncio.create_task(reg.handle_viewer(ws, "live-session"))
    await asyncio.sleep(0.02)
    ws.disconnect()
    await task
    assert "live-session" in reg.sessions, "a session with an active speaker must not be dropped"


async def test_multiple_viewers_all_tracked_and_cleaned_up_independently():
    reg = SessionRegistry()
    reg.speaker_connected("multi-viewer-session")
    wss = [FakeWebSocket() for _ in range(3)]
    tasks = [asyncio.create_task(reg.handle_viewer(ws, "multi-viewer-session")) for ws in wss]
    await asyncio.sleep(0.02)
    assert len(reg.sessions["multi-viewer-session"]) == 3

    wss[0].disconnect()
    await tasks[0]
    assert len(reg.sessions["multi-viewer-session"]) == 2

    wss[1].disconnect()
    wss[2].disconnect()
    await asyncio.gather(tasks[1], tasks[2])
    # Speaker is still "active" so the session itself survives even at 0 viewers.
    assert "multi-viewer-session" in reg.sessions
    assert len(reg.sessions["multi-viewer-session"]) == 0


async def test_broadcast_reaches_all_viewers():
    reg = SessionRegistry()
    reg.speaker_connected("broadcast-session")
    wss = [FakeWebSocket() for _ in range(3)]
    tasks = [asyncio.create_task(reg.handle_viewer(ws, "broadcast-session")) for ws in wss]
    await asyncio.sleep(0.02)

    await reg.broadcast("broadcast-session", {"text": "hello", "partial": False})
    for ws in wss:
        assert len(ws.sent) == 1
        assert '"hello"' in ws.sent[0]

    for ws in wss:
        ws.disconnect()
    await asyncio.gather(*tasks)


async def test_speaker_disconnected_broadcasts_ended_and_closes_viewers():
    reg = SessionRegistry()
    reg.speaker_connected("ending-session")
    ws = FakeWebSocket()
    task = asyncio.create_task(reg.handle_viewer(ws, "ending-session"))
    await asyncio.sleep(0.02)

    await reg.speaker_disconnected("ending-session")
    await task
    assert ws.close_code == 1000
    assert "ending-session" not in reg.sessions
    assert "ending-session" not in reg.active_speakers


async def test_access_code_required_rejects_viewer_without_code():
    reg = SessionRegistry()
    reg.speaker_connected("coded-session", access_code="secret1")
    ws = FakeWebSocket()
    await reg.handle_viewer(ws, "coded-session", access_code=None)
    assert ws.close_code == CLOSE_UNAUTHORIZED


async def test_access_code_required_rejects_wrong_code():
    reg = SessionRegistry()
    reg.speaker_connected("coded-session", access_code="secret1")
    ws = FakeWebSocket()
    await reg.handle_viewer(ws, "coded-session", access_code="wrongcode")
    assert ws.close_code == CLOSE_UNAUTHORIZED


async def test_access_code_required_admits_viewer_with_correct_code():
    reg = SessionRegistry()
    reg.speaker_connected("coded-session", access_code="secret1")
    ws = FakeWebSocket()
    task = asyncio.create_task(reg.handle_viewer(ws, "coded-session", access_code="secret1"))
    await asyncio.sleep(0.02)
    assert ws.close_code is None
    ws.disconnect()
    await task


async def test_no_code_set_admits_any_viewer():
    reg = SessionRegistry()
    reg.speaker_connected("public-session")  # no access_code
    ws = FakeWebSocket()
    task = asyncio.create_task(reg.handle_viewer(ws, "public-session", access_code="anything-or-nothing"))
    await asyncio.sleep(0.02)
    assert ws.close_code is None
    ws.disconnect()
    await task


async def test_max_viewers_per_session_enforced():
    reg = SessionRegistry(max_viewers_per_session=2, max_total_connections=200)
    reg.speaker_connected("capped-session")
    wss = [FakeWebSocket() for _ in range(4)]
    tasks = [asyncio.create_task(reg.handle_viewer(ws, "capped-session")) for ws in wss]
    await asyncio.sleep(0.05)

    admitted = [ws for ws in wss if ws.close_code is None]
    rejected = [ws for ws in wss if ws.close_code == CLOSE_AT_CAPACITY]
    assert len(admitted) == 2
    assert len(rejected) == 2

    for ws in admitted:
        ws.disconnect()
    await asyncio.gather(*tasks)


async def test_access_code_cleared_on_speaker_disconnect():
    reg = SessionRegistry()
    reg.speaker_connected("temp-session", access_code="secret1")
    await reg.speaker_disconnected("temp-session")
    assert "temp-session" not in reg.access_codes
