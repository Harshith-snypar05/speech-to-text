from app.plans import ADDON_NOTE, ADDON_PRICE_INR, ADDON_TAX_NOTE, BASIC, PLANS, PRO, with_gst


def test_with_gst_adds_18_percent():
    assert with_gst(999) == 1178.82
    assert with_gst(599) == 706.82
    assert with_gst(0) == 0


def test_pro_price_display_shows_base_price_plus_gst_suffix():
    assert PLANS[PRO].price_display == "₹999 + GST"


def test_basic_price_display_is_free_with_no_gst_shown():
    assert PLANS[BASIC].price_display == "Free"


def test_addon_note_shows_base_price_plus_gst_suffix():
    assert ADDON_PRICE_INR == 599
    assert f"₹{ADDON_PRICE_INR:,} {ADDON_TAX_NOTE}" in ADDON_NOTE
