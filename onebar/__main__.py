"""CLI: python -m onebar ask "storm before I'm back at the car?" --at 46.55,7.98 --return 17:00"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, time

from onebar.env import load_env
from onebar.facts.engine import Trip
from onebar.facts.open_meteo import ForecastError, fetch_forecast, local_now
from onebar.model.client import ModelError, TinkerDraft
from onebar.pipeline import answer


def _coords(text: str) -> tuple[float, float]:
    try:
        lat, lon = (float(p) for p in text.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("expected LAT,LON such as 46.55,7.98") from None
    return lat, lon


def _clock(text: str) -> time:
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        raise argparse.ArgumentTypeError("expected HH:MM in 24-hour time, such as 17:00") from None


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="onebar")
    sub = p.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask", help="answer one question")
    ask.add_argument("question")
    ask.add_argument("--at", type=_coords, required=True, metavar="LAT,LON")
    ask.add_argument("--return", dest="return_by", type=_clock, metavar="HH:MM", help="trip return time")
    ask.add_argument("--now", type=datetime.fromisoformat, metavar="ISO", help="local time override, for repeatable runs")
    ask.add_argument("--no-model", action="store_true", help="skip the model; the template answers")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    load_env()
    lat, lon = args.at
    try:
        forecast = fetch_forecast(lat, lon)
        at = args.now or local_now(forecast)
    except (ForecastError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    draft = None
    if not args.no_model:
        try:
            draft = TinkerDraft()
        except ModelError as exc:
            print(f"note: no model ({exc}); the template will answer", file=sys.stderr)
    trip = Trip(return_by=args.return_by) if args.return_by else None
    try:
        reply = answer(args.question, at, forecast, draft, trip=trip)
    except ValueError as exc:  # forecast does not cover the requested time
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(reply.text)
    r = reply.result
    print(f"[{reply.path}] {r.septets}/160 septets, {reply.latency_s:.2f}s, intents: {', '.join(r.intents)}", file=sys.stderr)
    for a in reply.attempts[:-1] if reply.path == "template" else reply.attempts:
        status = f"error: {a.error}" if a.error else ("pass" if a.result.passed else "fail " + ", ".join(a.result.reasons))
        print(f"  {a.source}: {status} -> {a.text!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
