"""Wire-format message builders and connection-param parsing, matching
what the Flutter clients speak (see
st_transcribe_app/lib/services/live_transcript_parser.dart).
"""
from urllib.parse import parse_qs, urlsplit


def partial_message(text: str) -> dict:
    return {"text": text, "partial": True}


def final_message(text: str) -> dict:
    return {"text": text, "partial": False}


def ended_message() -> dict:
    return {"type": "ended"}


def parse_connection_params(websocket) -> tuple[str, str | None]:
    query = urlsplit(websocket.request.path).query
    params = parse_qs(query)
    role = (params.get("role", ["speaker"])[0]).strip().lower()
    session_id = (params.get("session", [None])[0])
    return role, session_id
