from datetime import datetime

import pytest

from onebar import evaluation as E
from onebar import pipeline
from onebar.facts.engine import compute_facts
from onebar.model.client import ModelError
from conftest import set_hour, synth

AT = datetime(2026, 10, 8, 10, 20)
STORM = set_hour(synth(), "2026-10-08T14:00", weather_code=95)


class Script:
    def __init__(self, *outs):
        self.outs = list(outs)

    def __call__(self, prompt):
        o = self.outs.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


def scored(draft, q="storm before 3?", fc=STORM):
    facts = compute_facts(fc, AT, question=q)
    return E.score_row("r", pipeline.answer_from_facts(q, facts, draft), facts)


def test_first_try_pass_scores_clean():
    s = scored(Script("Storm from 14:00."))
    assert s.first_passed and s.path == "model" and s.groups_missing == 0 and not s.model_error


def test_invented_number_is_recorded_on_the_first_draft_not_the_final_reply():
    s = scored(Script("Storm at 88:88.", "Storm from 14:00."))
    assert s.path == "model-retry" and not s.first_passed
    assert any(r.startswith("invented_number") for r in s.first_reasons)
    assert s.reply == "Storm from 14:00."


def test_missing_group_is_counted():
    s = scored(Script("Gusts 20km/h.", "Storm from 14:00."))
    assert s.groups_demanded >= 1 and s.groups_missing == 1


def test_model_error_is_flagged_and_template_serves():
    s = scored(Script(ModelError("down")))
    assert s.model_error and s.path == "template"


def test_template_system_scores_as_all_pass():
    s = scored(None)
    assert s.first_passed and s.path == "template"


def test_aggregate_rates():
    rows = [
        scored(Script("Storm from 14:00.")),
        scored(Script("Storm at 88:88.", "Storm from 14:00.")),
        scored(Script("Storm at 88:88.", "No storm 77:77.")),
        scored(Script(ModelError("x"))),
    ]
    a = E.aggregate(rows, latencies=[1.0, 2.0, 3.0, 4.0])
    assert a["n"] == 4 and a["model_errors"] == 1
    assert a["first_try_pass"] == 0.25
    assert a["served_by_model"] == 0.5 and a["template_fallback"] == 0.5
    assert a["invented_number_rate"] == pytest.approx(2 / 3)  # the dead-endpoint row is not judged
    assert a["latency_p50_s"] == 2.0 and a["latency_p95_s"] == 4.0 and a["latency_n"] == 4
    assert a["septets_p95"] <= 160


def test_contradiction_rate():
    a = E.aggregate([scored(Script("No storm today.", "Storm from 14:00."))])
    assert a["contradiction_rate"] == 1.0


def test_required_fact_coverage_is_group_level():
    a = E.aggregate([scored(Script("Gusts 20km/h.", "Storm from 14:00."))])
    assert 0.0 <= a["required_fact_coverage"] < 1.0


def test_empty_input_does_not_divide_by_zero():
    a = E.aggregate([])
    assert a["n"] == 0 and a["first_try_pass"] == 0.0 and a["required_fact_coverage"] == 1.0


@pytest.mark.parametrize("vals, p, want", [([], 50, 0.0), ([5], 95, 5), ([1, 2, 3, 4], 50, 2), ([1, 2, 3, 4], 95, 4),
                                           (list(range(1, 101)), 95, 95)])
def test_percentile(vals, p, want):
    assert E.percentile(vals, p) == want


def test_cost_per_answer():
    price = {"prefill": 0.195, "sample": 0.60}
    assert E.cost_per_answer(1_000_000, 1_000_000, 1000, price) == pytest.approx((0.195 + 0.60) / 1000)
    assert E.cost_per_answer(10, 10, 0, price) == 0.0
    assert E.cost_per_answer(10, 10, 5, None) is None
