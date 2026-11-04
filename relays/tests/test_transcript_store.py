import core.transcript_store as transcript_store


def test_unknown_session_returns_none():
    assert transcript_store.get_session("never-started") is None
    assert transcript_store.get_history("never-started") == []


def test_start_session_then_record_events_then_end():
    transcript_store.start_session("sess1", access_code="abcd1234")
    transcript_store.record_event("sess1", "hello world")
    transcript_store.record_event("sess1", "second utterance")

    session = transcript_store.get_session("sess1")
    assert session is not None
    assert session["access_code"] == "abcd1234"
    assert session["ended_at"] is None
    assert transcript_store.get_history("sess1") == ["hello world", "second utterance"]

    transcript_store.end_session("sess1")
    assert transcript_store.get_session("sess1")["ended_at"] is not None
    # History survives past the end of the session.
    assert transcript_store.get_history("sess1") == ["hello world", "second utterance"]


def test_restarting_same_session_id_clears_its_old_history():
    transcript_store.start_session("reused", access_code=None)
    transcript_store.record_event("reused", "first run said this")
    transcript_store.end_session("reused")

    transcript_store.start_session("reused", access_code=None)
    assert transcript_store.get_history("reused") == []
    assert transcript_store.get_session("reused")["ended_at"] is None


def test_events_ordered_by_insertion_not_text():
    transcript_store.start_session("ordered", access_code=None)
    for text in ["zebra", "apple", "mango"]:
        transcript_store.record_event("ordered", text)
    assert transcript_store.get_history("ordered") == ["zebra", "apple", "mango"]
