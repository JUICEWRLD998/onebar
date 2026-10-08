import pytest

from onebar.check.intents import RawTime, classify, parse_target, required_groups


@pytest.mark.parametrize(
    "q,want",
    [
        ("storm before I'm back at the car?", ["storm", "turnaround"]),
        ("ridge by 3 then car ok?", ["turnaround", "go_nogo"]),
        ("any thunder today", ["storm"]),
        ("will it rain on the summit", ["rain"]),
        ("snow tonight?", ["rain"]),
        ("how windy is it up top", ["wind"]),
        ("gusts at 3pm?", ["wind"]),
        ("when is sunset", ["daylight"]),
        ("will it be dark by 6", ["daylight"]),
        ("how cold will it get", ["temperature"]),
        ("what are the temps", ["temperature"]),
        ("should I turn back", ["turnaround", "go_nogo"]),
        ("is it safe to go", ["go_nogo"]),
        ("STORM??", ["storm"]),
    ],
)
def test_classify(q, want):
    assert classify(q) == want


def test_classify_unknown_is_general():
    assert classify("hello") == ["general"]
    assert classify("") == ["general"]


def test_classify_does_not_match_inside_words():
    assert classify("the goal is the summit") == ["general"]
    assert classify("stormtrooper") == ["general"]


def test_classify_order_is_stable():
    assert classify("dark? windy? storm?") == ["storm", "wind", "daylight"]


def test_required_groups_per_intent():
    assert required_groups(["storm"]) == [("storm_first", "storm_none")]
    assert required_groups(["wind"]) == [("gust_max",)]
    assert required_groups(["rain"]) == [("rain_first", "rain_none", "pop_max")]
    assert required_groups(["daylight"]) == [("sunset", "dark_now")]
    assert required_groups(["temperature"]) == [("feels_min", "temp_now")]


def test_required_groups_dedupe_and_order():
    groups = required_groups(["turnaround", "go_nogo"])
    assert groups == [
        ("turn_by", "car_by", "target", "turn_now", "sunset"),
        ("storm_first", "storm_none"),
        ("gust_max",),
    ]


def test_required_groups_general():
    assert required_groups(["general"]) == [("storm_first", "storm_none")]


@pytest.mark.parametrize(
    "q,want",
    [
        ("ridge by 3 then car ok?", RawTime(3, 0, None)),
        ("back at 15:30", RawTime(15, 30, None)),
        ("back by 5pm", RawTime(5, 0, "pm")),
        ("done before 11:15 am", RawTime(11, 15, "am")),
        ("summit at 9", RawTime(9, 0, None)),
        ("until 12", RawTime(12, 0, None)),
    ],
)
def test_parse_target(q, want):
    assert parse_target(q) == want


@pytest.mark.parametrize(
    "q",
    ["storm today?", "wind at 3000m", "by 99", "at 25:00", "at 80% chance", "by 7:99", "hello"],
)
def test_parse_target_none(q):
    assert parse_target(q) is None
