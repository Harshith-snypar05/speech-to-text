from core.transcript_manager import collapse_repetition


def test_no_repetition_unchanged():
    assert collapse_repetition("ask not what your country can do for you") == \
        "ask not what your country can do for you"


def test_collapses_single_word_repetition():
    assert collapse_repetition("no, no, no, no, I don't want that") == "no, I don't want that"


def test_collapses_multi_word_repetition():
    text = "a little bit of a little bit of a little bit of cake"
    assert collapse_repetition(text) == "a little bit of cake"


def test_two_repeats_not_collapsed():
    # Pattern requires 3+ repeats ({2,} after the first) -- two occurrences
    # of a phrase is normal language, not a hallucination loop.
    text = "very very tired"
    assert collapse_repetition(text) == text


def test_empty_string():
    assert collapse_repetition("") == ""


def test_case_insensitive_repetition():
    assert collapse_repetition("No, NO, no, no, stop") == "No, stop"
