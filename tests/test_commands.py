from datetime import time

import pytest

from onebar import commands as C
from onebar.check.gsm7 import LIMIT, analyze
from onebar.facts.locate import Place, geocode


def test_help_text_fits_one_sms_in_gsm7():
    a = analyze(C.HELP_TEXT)
    assert not a.bad_chars and a.septets <= LIMIT, a


@pytest.mark.parametrize("text, cls", [
    ("OUT", C.OutCmd), ("out", C.OutCmd), ("  Out. ", C.OutCmd), ("out!", C.OutCmd),
    ("FORGET", C.ForgetCmd), ("forget", C.ForgetCmd), ("HELP", C.HelpCmd), ("help!", C.HelpCmd),
])
def test_single_word_commands(text, cls):
    assert isinstance(C.parse(text), cls)


@pytest.mark.parametrize("text", ["outside?", "out of signal, storm?", "help me, is it safe", "forget it, storm by 3?"])
def test_a_command_word_inside_a_question_stays_a_question(text):
    assert isinstance(C.parse(text), C.QuestionCmd)


def test_trip_with_a_place_name():
    c = C.parse("TRIP Aletschhorn BACK 17:30 CONTACT sam@example.org")
    assert c == C.TripCmd("Aletschhorn", None, time(17, 30), "sam@example.org")


def test_trip_is_case_insensitive_and_takes_multiword_places_and_coordinates():
    c = C.parse("trip Ben Nevis summit back 6:05 contact +44 7700 900123")
    assert c.place == "Ben Nevis summit" and c.back == time(6, 5) and c.contact == "+44 7700 900123" and c.coords is None
    d = C.parse("Trip 46.55, 7.98 BACK 17:00 CONTACT a@b.co")
    assert d.coords == (46.55, 7.98)
    e = C.parse("TRIP -51.0,-73.0 BACK 09:00 CONTACT a@b.co")
    assert e.coords == (-51.0, -73.0)


@pytest.mark.parametrize("text", [
    "TRIP",
    "TRIP Matterhorn",
    "TRIP Matterhorn BACK 17:00",
    "TRIP BACK 17:00 CONTACT a@b.co",
    "TRIP Matterhorn BACK 25:00 CONTACT a@b.co",
    "TRIP Matterhorn BACK 17:61 CONTACT a@b.co",
    "TRIP Matterhorn BACK 5pm CONTACT a@b.co",
    "TRIP Matterhorn BACK 17:00 CONTACT nobody",
    "TRIP Matterhorn BACK 17:00 CONTACT 12",
    "TRIP 95,10 BACK 17:00 CONTACT a@b.co",
    "TRIP 10,200 BACK 17:00 CONTACT a@b.co",
])
def test_malformed_trips_are_bad_with_a_usable_reason(text):
    c = C.parse(text)
    assert isinstance(c, C.BadCmd) and "TRIP" in c.reason
    a = analyze(c.reason)
    assert not a.bad_chars and a.septets <= 320  # at most two SMS segments


def test_phone_contacts_are_refused_when_no_sms_channel_exists():
    text = "TRIP 46.5,7.9 BACK 17:00 CONTACT +44 7700 900123"
    assert isinstance(C.parse(text), C.TripCmd)  # allowed by default
    bad = C.parse(text, allow_phone=False)
    assert isinstance(bad, C.BadCmd) and "email address" in bad.reason and "phone" not in bad.reason
    assert isinstance(C.parse("TRIP 46.5,7.9 BACK 17:00 CONTACT a@b.co", allow_phone=False), C.TripCmd)
    assert isinstance(C.parse("TRIP 46.5,7.9 BACK 17:00 CONTACT nobody", allow_phone=False), C.BadCmd)


def test_empty_and_overlong_messages():
    assert isinstance(C.parse(""), C.BadCmd) and isinstance(C.parse("   "), C.BadCmd)
    assert isinstance(C.parse("x" * (C.MAX_LEN + 1)), C.BadCmd)
    assert isinstance(C.parse("x" * C.MAX_LEN), C.QuestionCmd)


def test_question_keeps_its_text():
    assert C.parse("  storm before 3? ") == C.QuestionCmd("storm before 3?")


def test_a_trip_word_prefix_is_not_a_trip():
    assert isinstance(C.parse("tripod ok?"), C.QuestionCmd)


# ---- geocode -------------------------------------------------------------------------------------------------

def test_geocode_picks_the_first_result():
    seen = []

    def get(url):
        seen.append(url)
        return {"results": [{"name": "Zermatt", "latitude": 46.02, "longitude": 7.75, "country": "Switzerland"}]}

    p = geocode("Zermatt area", get)
    assert p == Place("Zermatt, Switzerland", 46.02, 7.75)
    assert "name=Zermatt%20area" in seen[0] and "count=1" in seen[0]


@pytest.mark.parametrize("payload", [{}, {"results": []}, None, {"results": [{"name": "x"}]}])
def test_geocode_no_match_is_none(payload):
    assert geocode("nowhere", lambda u: payload) is None


def test_geocode_blank_name_makes_no_request():
    def get(url):
        raise AssertionError("no request expected")

    assert geocode("   ", get) is None


def test_geocode_network_errors_propagate_for_the_activity_to_retry():
    def get(url):
        raise OSError("down")

    with pytest.raises(OSError):
        geocode("Zermatt", get)
