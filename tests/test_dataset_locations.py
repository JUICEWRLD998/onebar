import pytest

from onebar.dataset import locations as L
from onebar.dataset.splits import assign, cell, split_of

REGION = L.Region("alps_test", "alpine", (46.0, 7.0, 47.0, 8.0))


def el(id_, name, lat, lon, **tags):
    return {"type": "node", "id": id_, "lat": lat, "lon": lon, "tags": {"name": name, **tags}}


ELEMENTS = [
    el(1, "Alpha Peak", 46.1, 7.1, natural="peak", ele="3000"),
    el(2, "Alpha Peak", 46.1001, 7.1001, natural="peak", ele="3000"),  # duplicate of 1
    el(3, "Beta Hut", 46.2, 7.2, tourism="alpine_hut"),
    el(4, "Gamma Trailhead", 46.3, 7.3, highway="trailhead"),
    {"type": "node", "id": 5, "lat": 46.4, "lon": 7.4, "tags": {"natural": "peak", "ele": "2500"}},  # no name
    el(6, "Delta", 46.5, 7.5, amenity="cafe"),  # not a hiking kind
    el(7, "Echo Peak", 46.6, 7.6, natural="peak"),  # no ele is fine
]


def test_parse_keeps_named_hiking_nodes_and_dedupes():
    locs = L.parse_elements(ELEMENTS, REGION)
    assert [x.name for x in locs] == ["Alpha Peak", "Beta Hut", "Gamma Trailhead", "Echo Peak"]
    assert {x.kind for x in locs} == {"peak", "hut", "trailhead"}
    assert all(x.region == "alps_test" for x in locs)
    assert locs[0].id == "osm:n1" and locs[0].lat == 46.1 and locs[0].ele == 3000.0
    assert locs[-1].ele is None


def test_parse_survives_a_malformed_elevation():
    bad = [el(9, "Odd Peak", 46.7, 7.7, natural="peak", ele="about 3000")]
    assert L.parse_elements(bad, REGION)[0].ele is None


def test_sample_is_seeded_capped_and_keeps_every_kind_when_possible():
    locs = L.parse_elements(ELEMENTS, REGION)
    a = L.sample(locs, 3, seed=1)
    b = L.sample(locs, 3, seed=1)
    assert [x.id for x in a] == [x.id for x in b] and len(a) == 3
    assert {"hut", "trailhead"} <= {x.kind for x in a}  # peaks must not crowd the others out
    assert L.sample(locs, 99, seed=1) == locs


def test_jsonl_roundtrip(tmp_path):
    locs = L.parse_elements(ELEMENTS, REGION)
    p = tmp_path / "l.jsonl"
    L.write_jsonl(locs, p)
    assert L.read_jsonl(p) == locs


def test_regions_are_valid_boxes_with_unique_names():
    names = [r.name for r in L.REGIONS]
    assert len(names) == len(set(names)) >= 35
    for r in L.REGIONS:
        s, w, n, e = r.bbox
        assert -90 <= s < n <= 90 and -180 <= w < e <= 180, r.name


def test_query_names_the_three_kinds_and_the_box():
    q = L.build_query((1.5, 2.5, 3.5, 4.5))
    assert "(1.5,2.5,3.5,4.5)" in q
    for tag in ('"natural"="peak"', '"highway"="trailhead"', '"tourism"="alpine_hut"'):
        assert tag in q


def test_fetch_region_retries_then_returns_elements(monkeypatch):
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    calls = []

    def post(q):
        calls.append(q)
        if len(calls) < 3:
            raise OSError("429")
        return {"elements": [1, 2]}

    assert L.fetch_region(REGION, post=post) == [1, 2] and len(calls) == 3


def test_fetch_region_gives_up_loudly(monkeypatch):
    monkeypatch.setattr(L.time, "sleep", lambda s: None)

    def post(q):
        raise OSError("down")

    with pytest.raises(RuntimeError, match="alps_test"):
        L.fetch_region(REGION, post=post, retries=2)


def test_split_is_deterministic_and_roughly_80_10_10():
    counts = {"train": 0, "val": 0, "test": 0}
    n = 0
    for i in range(-80, 80):
        for j in range(-170, 170, 3):
            counts[split_of(i + 0.25, j + 0.25)] += 1
            n += 1
    assert 0.74 < counts["train"] / n < 0.86
    assert 0.06 < counts["val"] / n < 0.14 and 0.06 < counts["test"] / n < 0.14
    assert split_of(46.55, 7.98) == split_of(46.55, 7.98)


def test_nearby_points_share_a_cell_and_so_a_split():
    assert cell(46.55, 7.98) == cell(46.70, 7.60) == cell(46.51, 7.51)
    assert split_of(46.55, 7.98) == split_of(46.70, 7.60)
    assert cell(46.55, 7.98) != cell(47.05, 7.98)


def test_assign_never_puts_a_cell_in_two_splits():
    locs = L.parse_elements(ELEMENTS, REGION)
    by_split = assign(locs)
    seen = {}
    for s, items in by_split.items():
        for x in items:
            assert seen.setdefault(cell(x.lat, x.lon), s) == s
    assert sum(len(v) for v in by_split.values()) == len(locs)
