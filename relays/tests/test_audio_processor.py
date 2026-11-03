from core.audio_processor import UtteranceBuffer

from .conftest import make_speech_chunk


def _buf(**overrides):
    defaults = dict(
        sample_rate=16000, bytes_per_sample=2, silence_rms_threshold=0.01,
        silence_hang_seconds=0.6, min_utterance_seconds=0.3, max_utterance_seconds=8.0,
    )
    defaults.update(overrides)
    return UtteranceBuffer(**defaults)


def test_silence_does_not_trigger_boundary():
    buf = _buf()
    assert buf.add_chunk(make_speech_chunk(amplitude=0.001)) is False
    assert buf.speech_s == 0
    assert not buf.has_pending_utterance()


def test_speech_then_enough_silence_triggers_boundary():
    buf = _buf()
    # 0.5s of speech (>= min_utterance_seconds)
    for _ in range(5):
        buf.add_chunk(make_speech_chunk(amplitude=0.5, seconds=0.1))
    assert buf.has_pending_utterance()
    # Now enough silence to cross silence_hang_seconds (0.6s)
    boundary = False
    for _ in range(7):
        boundary = buf.add_chunk(make_speech_chunk(amplitude=0.001, seconds=0.1)) or boundary
    assert boundary is True


def test_short_blip_below_min_utterance_does_not_count_as_pending():
    buf = _buf()
    buf.add_chunk(make_speech_chunk(amplitude=0.5, seconds=0.1))  # only 0.1s, < 0.3s min
    assert not buf.has_pending_utterance()


def test_max_utterance_forces_boundary_without_silence():
    buf = _buf(max_utterance_seconds=0.5)
    boundary = False
    for _ in range(10):  # 1.0s of continuous speech, no pause
        boundary = buf.add_chunk(make_speech_chunk(amplitude=0.5, seconds=0.1)) or boundary
    assert boundary is True


def test_take_resets_state_and_returns_snapshot():
    buf = _buf()
    buf.add_chunk(make_speech_chunk(amplitude=0.5))
    snapshot = buf.take()
    assert len(snapshot) > 0
    assert buf.buffer == bytearray()
    assert buf.silence_s == 0
    assert buf.speech_s == 0


def test_adaptive_mode_off_by_default():
    buf = _buf()
    assert buf.adaptive_noise_floor is False
    assert buf._effective_threshold() == 0.01


def test_adaptive_mode_converges_to_ambient_noise_without_misclassifying_as_speech():
    buf = _buf(adaptive_noise_floor=True, noise_floor_multiplier=2.5)
    for _ in range(50):
        buf.add_chunk(make_speech_chunk(amplitude=0.02, seconds=0.1))
    assert buf.speech_s == 0, "sustained ambient noise must never be classified as speech"
    assert abs(buf._noise_floor - 0.02) < 0.002


def test_adaptive_mode_still_detects_real_speech_over_elevated_floor():
    buf = _buf(adaptive_noise_floor=True, noise_floor_multiplier=2.5)
    for _ in range(50):
        buf.add_chunk(make_speech_chunk(amplitude=0.02, seconds=0.1))
    buf.add_chunk(make_speech_chunk(amplitude=0.3, seconds=0.1))
    assert buf.speech_s > 0


def test_adaptive_mode_never_drops_below_configured_floor():
    buf = _buf(adaptive_noise_floor=True, noise_floor_multiplier=2.5)
    for _ in range(30):
        buf.add_chunk(make_speech_chunk(amplitude=0.0005, seconds=0.1))
    assert buf._effective_threshold() == 0.01
