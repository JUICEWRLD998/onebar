import argparse
import json
from datetime import time
from pathlib import Path

import pytest

from onebar import __main__ as cli
from conftest import FIXTURE_DIR


def test_coords_and_clock_parsers():
    assert cli._coords("46.55,7.98") == (46.55, 7.98)
    assert cli._coords("-51,-73") == (-51.0, -73.0)
    assert cli._clock("17:05") == time(17, 5)
    for bad in ("46.55", "a,b", "1,2,3"):
        with pytest.raises(argparse.ArgumentTypeError):
            cli._coords(bad)
    for bad in ("5pm", "25:00", "17"):
        with pytest.raises(argparse.ArgumentTypeError):
            cli._clock(bad)


@pytest.fixture
def offline(monkeypatch):
    blob = json.loads((FIXTURE_DIR / "01_jungfrau_ch.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cli, "fetch_forecast", lambda lat, lon: blob["forecast"])
    monkeypatch.setattr(cli, "load_env", lambda: None)
    return blob


def test_ask_without_model_prints_a_checked_template_reply(offline, capsys):
    rc = cli.main(["ask", "turn around time?", "--at", "46.55,7.98", "--return", "17:00",
                   "--now", "2026-10-08T10:20", "--no-model"])
    out = capsys.readouterr()
    assert rc == 0
    assert "15:30" in out.out and out.out.count("\n") == 1
    assert "[template]" in out.err


def test_ask_out_of_range_time_is_a_clean_error(offline, capsys):
    rc = cli.main(["ask", "storm?", "--at", "46.55,7.98", "--now", "2031-01-01T10:00", "--no-model"])
    assert rc == 1
    assert "does not cover" in capsys.readouterr().err


def test_ask_forecast_failure_is_a_clean_error(monkeypatch, capsys):
    def boom(lat, lon):
        raise cli.ForecastError("down")

    monkeypatch.setattr(cli, "fetch_forecast", boom)
    monkeypatch.setattr(cli, "load_env", lambda: None)
    assert cli.main(["ask", "storm?", "--at", "1,2", "--no-model"]) == 1
    assert "down" in capsys.readouterr().err


def test_missing_key_degrades_to_template(offline, monkeypatch, capsys):
    monkeypatch.delenv("TINKER_API_KEY", raising=False)
    rc = cli.main(["ask", "storm?", "--at", "46.55,7.98", "--now", "2026-10-08T10:20"])
    out = capsys.readouterr()
    assert rc == 0 and "[template]" in out.err and "TINKER_API_KEY" in out.err
