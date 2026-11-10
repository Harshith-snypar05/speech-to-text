"""Wire-format message builders and connection-param parsing, matching
what the Flutter clients speak (see
st_transcribe_app/lib/services/live_transcript_parser.dart).
"""
import re
from urllib.parse import parse_qs, urlsplit

_SESSION_ID_RE = re.compile(r'^[A-Za-z0-9_-]{6,64}$')
_ACCESS_CODE_RE = re.compile(r'^[A-Za-z0-9]{4,32}$')
_VALID_ROLES = {"speaker", "viewer"}


def partial_message(text: str) -> dict:
    return {"text": text, "partial": True}


def final_message(text: str) -> dict:
    return {"text": text, "partial": False}


def refine_message(seq: int, original: str, refined: str) -> dict:
    """Replace an already-sent final. Deliberately has no "text" key: clients that predate it ignore the message instead
    of showing it as a new line. `original` identifies the line, so clients need not count finals (joins, reconnects)."""
    return {"type": "refine", "seq": seq, "original": original, "refined": refined}


def ended_message() -> dict:
    return {"type": "ended"}


def is_valid_session_id(session_id: str | None) -> bool:
    return bool(session_id) and bool(_SESSION_ID_RE.match(session_id))


def is_valid_access_code(code: str | None) -> bool:
    """None (no code supplied) is valid -- code is optional. A supplied
    code must still match the expected shape."""
    return code is None or bool(_ACCESS_CODE_RE.match(code))


class ConnectionParams:
    __slots__ = ("role", "session_id", "access_code", "token")

    def __init__(self, role: str, session_id: str | None, access_code: str | None, token: str | None = None):
        self.role = role
        self.session_id = session_id
        self.access_code = access_code
        self.token = token


def parse_connection_params(websocket) -> ConnectionParams:
    query = urlsplit(websocket.request.path).query
    params = parse_qs(query)
    role = (params.get("role", ["speaker"])[0]).strip().lower()
    if role not in _VALID_ROLES:
        role = "speaker"
    session_id = params.get("session", [None])[0]
    access_code = params.get("code", [None])[0]
    return ConnectionParams(role, session_id, access_code, params.get("token", [None])[0])
