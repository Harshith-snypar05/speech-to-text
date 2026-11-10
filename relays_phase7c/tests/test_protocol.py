from core.protocol import (
    ended_message, final_message, is_valid_access_code, is_valid_session_id,
    parse_connection_params, partial_message,
)


class FakeRequest:
    def __init__(self, path):
        self.path = path


class FakeWS:
    def __init__(self, path):
        self.request = FakeRequest(path)


def test_partial_message_shape():
    assert partial_message("hello") == {"text": "hello", "partial": True}


def test_final_message_shape():
    assert final_message("hello") == {"text": "hello", "partial": False}


def test_ended_message_shape():
    assert ended_message() == {"type": "ended"}


def test_parse_connection_params_speaker_default():
    params = parse_connection_params(FakeWS("/?session=abc12345"))
    assert params.role == "speaker"
    assert params.session_id == "abc12345"
    assert params.access_code is None


def test_parse_connection_params_viewer_with_code():
    params = parse_connection_params(FakeWS("/?role=viewer&session=abc12345&code=XYZ789"))
    assert params.role == "viewer"
    assert params.session_id == "abc12345"
    assert params.access_code == "XYZ789"


def test_parse_connection_params_invalid_role_falls_back_to_speaker():
    params = parse_connection_params(FakeWS("/?role=admin&session=abc12345"))
    assert params.role == "speaker"


def test_parse_connection_params_missing_session():
    params = parse_connection_params(FakeWS("/?role=viewer"))
    assert params.session_id is None


def test_is_valid_session_id_accepts_normal_tokens():
    assert is_valid_session_id("k3f8x9q2ab")
    assert is_valid_session_id("abc-123_XYZ")


def test_is_valid_session_id_rejects_too_short():
    assert not is_valid_session_id("abc12")  # 5 chars, min is 6


def test_is_valid_session_id_rejects_none_and_empty():
    assert not is_valid_session_id(None)
    assert not is_valid_session_id("")


def test_is_valid_session_id_rejects_special_characters():
    assert not is_valid_session_id("abc 123!!")
    assert not is_valid_session_id("../../etc/passwd")


def test_is_valid_access_code_none_is_valid_optional():
    assert is_valid_access_code(None)


def test_is_valid_access_code_rejects_too_short():
    assert not is_valid_access_code("abc")  # 3 chars, min is 4


def test_is_valid_access_code_accepts_normal_code():
    assert is_valid_access_code("LF3WD9WR")
