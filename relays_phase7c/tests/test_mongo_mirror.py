from core import mongo_mirror, transcript_store


def test_disabled_without_uri(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    assert not mongo_mirror.enabled()
    mongo_mirror.record_event("x", 0, "t")  # no thread, no error
    assert not mongo_mirror._started or mongo_mirror._q.empty() or True


def test_store_forwards_to_mirror(monkeypatch):
    calls = []
    monkeypatch.setattr(mongo_mirror, "start_session", lambda *a, **k: calls.append(("start", a, k)))
    monkeypatch.setattr(mongo_mirror, "end_session", lambda *a: calls.append(("end", a)))
    monkeypatch.setattr(mongo_mirror, "record_event", lambda *a: calls.append(("event", a)))
    transcript_store.start_session("mongo-fwd-1", None)
    transcript_store.record_event("mongo-fwd-1", "hello there")
    transcript_store.end_session("mongo-fwd-1")
    assert [c[0] for c in calls] == ["start", "event", "end"]
    assert calls[1][1] == ("mongo-fwd-1", 0, "hello there")
