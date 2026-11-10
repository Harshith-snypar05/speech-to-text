"""Spoken numbers -> digits, and the tightened refinement guard (cases taken from real staging sessions)."""
import pytest

from core.numbers import to_digits
from core.refiner import refine_text


@pytest.mark.parametrize("spoken,digits", [
    ("seven hundred and eighty one", "781"),
    ("Seven eight one B", "781 B"),
    ("One two three four five six.", "123456."),
    ("nine zero one four eight two five double zero seven", "9014825007"),
    ("two sixty two", "262"),
    ("twenty twenty five", "2025"),
    ("two thousand and twenty five", "2025"),
    ("twenty-five", "25"),
    ("three hundred", "300"),
    ("one thousand two hundred", "1200"),
    ("fifteen minutes", "15 minutes"),
    ("call me on nine zero one, then five", "call me on 901, then five"),  # comma ends a number; lone digit word stays
])
def test_converts(spoken, digits):
    assert to_digits(spoken) == digits


@pytest.mark.parametrize("text", [
    "one of them", "I have five apples", "that is nine hundred and forty eight hundred and twenty five",
    "hundred", "a thousand", "no numbers here", "", "tone zone",
])
def test_leaves_alone(text):
    assert to_digits(text) == text


def test_guard_accepts_formatting_and_number_fixes():
    assert refine_text("hello can you hear me", "Hello, can you hear me?") == "Hello, can you hear me?"
    assert refine_text("one two three four five", "One two three four five.") == "12345."
    assert refine_text("i would like to tell my phone number", "I would like to uh tell my phone number.") \
        == "I would like to uh tell my phone number."  # filler kept, but it never counts against the guard


def test_guard_accepts_small_word_correction_in_a_long_sentence():
    eou = "i really love this transcription and it is really pathet and accurate and also the text refinement all are so good"
    nem = "I really love this transcription and it is really faster and accurate and also the text refinement all are so good."
    assert refine_text(eou, nem) == nem


def test_guard_rejects_cases_seen_on_the_phone():
    # cut-off name, short utterance with changed word
    assert refine_text("hello guys myself harcel", "Hello guys, uh, myself Harce") is None
    # invented leading word + several changes
    assert refine_text("the android app on smg seven hundred and eighty one b opens crypt",
                       "Tet the Android app on SMG seven eight one B open script live") is None
    # different sentence / garbage / truncation
    assert refine_text("hello can you hear me", "thank you for watching see you next time") is None
    assert refine_text("one two three four five six", "one") is None
    assert refine_text("so i would like the third session called", "So I would like to start a session call") is None
    assert refine_text("this is so good", "This is so great") is None  # short: only formatting may change
    assert refine_text("hello there", "hello there") is None
