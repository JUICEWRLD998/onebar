import threading
from datetime import datetime, time, timedelta, timezone

import pytest

from onebar import trips
from onebar.channels.outbox import OutboxSender
from onebar.check.gsm7 import LIMIT, analyze

UTC = timezone.utc


# ---- deadline ------------------------------------------------------------------------------------------------

def test_deadline_later_today_in_the_place_clock():
    now = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)  # 10:00 in UTC+2
    d = trips.deadline_utc(now, 7200, time(17, 0))
    assert d == datetime(2026, 7, 14, 15, 0, tzinfo=UTC)  # 17:00 local
    assert trips.local_clock(d, 7200) == "17:00"


def test_deadline_already_passed_means_tomorrow():
    now = datetime(2026, 7, 14, 16, 0, tzinfo=UTC)  # 18:00 local
    assert trips.deadline_utc(now, 7200, time(17, 0)) == datetime(2026, 7, 15, 15, 0, tzinfo=UTC)


def test_deadline_equal_to_now_means_tomorrow_not_instant_alert():
    now = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)
    assert trips.deadline_utc(now, 7200, time(17, 0)) - now == timedelta(hours=24)


def test_deadline_uses_the_places_date_not_utcs():
    # 23:30 UTC on the 14th is already 05:00 on the 15th in UTC+5:30; 17:00 local that day is 11:30 UTC on the 15th
    now = datetime(2026, 7, 14, 23, 30, tzinfo=UTC)
    assert trips.deadline_utc(now, 19800, time(17, 0)) == datetime(2026, 7, 15, 11, 30, tzinfo=UTC)


def test_deadline_negative_offset_and_aware_input_in_another_zone():
    now = datetime(2026, 7, 14, 12, 0, tzinfo=timezone(timedelta(hours=-7)))  # 19:00 UTC, 12:00 in UTC-7
    d = trips.deadline_utc(now, -7 * 3600, time(15, 0))
    assert d == datetime(2026, 7, 14, 22, 0, tzinfo=UTC)


@pytest.mark.parametrize("offset", [-12 * 3600, -3 * 3600, 0, 5 * 3600 + 1800, 12 * 3600 + 2700])
def test_deadline_is_always_within_a_day_ahead_and_reads_back_as_the_asked_time(offset):
    for hour in range(0, 24, 5):
        now = datetime(2026, 3, 29, hour, 17, tzinfo=UTC)
        d = trips.deadline_utc(now, offset, time(9, 30))
        assert timedelta(0) < d - now <= timedelta(hours=24)
        assert trips.local_clock(d, offset) == "09:30"


# ---- texts ---------------------------------------------------------------------------------------------------

def test_trip_saved_text_fits_one_sms():
    a = analyze(trips.trip_saved_text("17:00", "17:30"))
    assert not a.bad_chars and a.septets <= LIMIT, a


@pytest.mark.parametrize("text", [trips.NEED_PLACE, trips.FORECAST_DOWN])
def test_fixed_replies_fit_one_sms(text):
    a = analyze(text)
    assert not a.bad_chars and a.septets <= LIMIT, a


def test_alert_says_it_is_not_a_rescue_service_and_names_the_facts():
    t = trips.alert_text("sam@example.org", "Zermatt, Switzerland", 46.0207, 7.7491, "17:00", "14:12")
    assert "not a rescue service" in t and "17:00" in t and "14:12" in t
    assert "46.021" in t and "7.749" in t and "sam@example.org" in t
    assert "No message" in trips.alert_text("s", "p", 1.0, 2.0, "17:00", None)


def test_alert_does_not_print_coordinates_twice_when_the_place_is_coordinates():
    t = trips.alert_text("s", "46.550,7.980", 46.55, 7.98, "17:00", None)
    assert t.count("46.550") == 1 and "Trip area: 46.550, 7.980." in t


# ---- outbox --------------------------------------------------------------------------------------------------

def test_outbox_sends_a_key_once(tmp_path):
    box = OutboxSender(tmp_path / "out.jsonl")
    assert box.send("k1", "a@b.co", "hello") is True
    assert box.send("k1", "a@b.co", "hello again") is False
    assert box.send("k2", "a@b.co", "second") is True
    rows = box.sent()
    assert [r["key"] for r in rows] == ["k1", "k2"] and rows[0]["text"] == "hello" and rows[0]["to"] == "a@b.co"


def test_outbox_remembers_across_instances(tmp_path):
    p = tmp_path / "out.jsonl"
    OutboxSender(p).send("k", "x", "t")
    assert OutboxSender(p).send("k", "x", "t") is False  # a restarted worker


def test_outbox_survives_a_torn_line(tmp_path):
    p = tmp_path / "out.jsonl"
    OutboxSender(p).send("good", "x", "t")
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"key": "torn", "to": ')  # crash mid-write, no newline
    box = OutboxSender(p)
    assert [r["key"] for r in box.sent()] == ["good"]
    assert box.send("torn", "x", "t") is True  # a torn line is not a sent message


def test_outbox_is_safe_under_concurrent_sends_of_one_key(tmp_path):
    box = OutboxSender(tmp_path / "out.jsonl")
    results = []
    threads = [threading.Thread(target=lambda: results.append(box.send("same", "x", "t"))) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1 and len(box.sent()) == 1


def test_outbox_keeps_non_ascii_text_intact(tmp_path):
    box = OutboxSender(tmp_path / "out.jsonl")
    box.send("k", "x", "Zürich 5°C")
    assert box.sent()[0]["text"] == "Zürich 5°C"
