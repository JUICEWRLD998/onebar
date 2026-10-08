import pytest

from onebar.check.gsm7 import BASIC, EXTENSION, LIMIT, analyze, septets


def test_tables_are_well_formed():
    assert len(BASIC) == 127
    assert len(EXTENSION) == 9
    assert not set(BASIC) & set(EXTENSION)


def test_limit_is_160():
    assert LIMIT == 160


def test_plain_ascii_counts_one_each():
    assert septets("Storm 14:40, gusts 55km/h.") == 26


def test_boundary_159_160_161():
    assert analyze("a" * 159).septets == 159
    assert analyze("a" * 159).fits
    assert analyze("a" * 160).septets == 160
    assert analyze("a" * 160).fits
    assert analyze("a" * 161).septets == 161
    assert not analyze("a" * 161).fits


@pytest.mark.parametrize("ch", ["^", "{", "}", "\\", "[", "~", "]", "|", "€"])
def test_extension_chars_count_two(ch):
    assert septets(ch) == 2


def test_extension_set_matches_the_spec_list():
    assert EXTENSION == frozenset(["^", "{", "}", "\\", "[", "~", "]", "|", "€"])


def test_one_extension_char_pushes_159_to_161():
    assert septets("a" * 158 + "[") == 160
    assert analyze("a" * 158 + "[").fits
    over = "a" * 159 + "["
    assert septets(over) == 161
    assert not analyze(over).fits


@pytest.mark.parametrize(
    "ch",
    ["\U0001F600", "°", "’", "“", "—", "…", "ç", "中"],
)
def test_non_gsm_rejected(ch):
    res = analyze("ok " + ch)
    assert ch in res.bad_chars
    assert not res.fits


def test_gsm_accented_letters_allowed():
    assert analyze("café ü ñ").bad_chars == ()


def test_degree_sign_is_not_gsm_but_euro_is():
    assert analyze("5°").bad_chars == ("°",)
    assert analyze("5€").bad_chars == ()


def test_newline_is_one_septet():
    assert septets("a\nb") == 3


def test_form_feed_rejected():
    assert "\f" in analyze("a\fb").bad_chars


def test_empty_fits_with_zero():
    res = analyze("")
    assert res.septets == 0 and res.fits


def test_bad_chars_deduplicated_in_order():
    assert analyze("° x \U0001F600 °").bad_chars == ("°", "\U0001F600")


def test_combining_accent_is_rejected_not_normalised():
    assert not analyze("é").fits
