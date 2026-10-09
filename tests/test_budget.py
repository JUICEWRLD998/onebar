import json

import pytest

from onebar.budget import BudgetExceeded, Ledger

PRICES = {"cheap": {"prefill": 1.0, "sample": 2.0}}


def ledger(tmp_path, cap):
    return Ledger(tmp_path / "spend.json", cap_usd=cap, prices=PRICES)


def test_cost_uses_per_million_prices(tmp_path):
    assert ledger(tmp_path, 1).cost("cheap", 1_000_000, 500_000) == pytest.approx(2.0)


def test_charges_accumulate_and_persist_across_instances(tmp_path):
    a = ledger(tmp_path, 10)
    a.charge("cheap", 1_000_000, 0)
    a.charge("cheap", 0, 1_000_000)
    b = ledger(tmp_path, 10)  # a restarted script
    assert b.spent() == pytest.approx(3.0)
    data = json.loads((tmp_path / "spend.json").read_text())
    assert data["calls"] == 2 and data["by_model"]["cheap"]["calls"] == 2


def test_check_refuses_when_one_more_call_would_pass_the_cap(tmp_path):
    led = ledger(tmp_path, 1.0)
    led.charge("cheap", 900_000, 0)  # $0.90 spent
    with pytest.raises(BudgetExceeded, match="cap"):
        led.check("cheap", est_prompt_tokens=200_000, est_completion_tokens=0)  # +$0.20
    led.check("cheap", est_prompt_tokens=50_000, est_completion_tokens=0)  # +$0.05 fits


def test_unknown_model_is_refused_rather_than_billed_at_zero(tmp_path):
    with pytest.raises(BudgetExceeded, match="no price"):
        ledger(tmp_path, 1).check("mystery")


def test_corrupt_ledger_file_restarts_from_zero_not_a_crash(tmp_path):
    (tmp_path / "spend.json").write_text("{not json")
    assert ledger(tmp_path, 1).spent() == 0.0


def test_concurrent_charges_do_not_lose_updates(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    led = ledger(tmp_path, 100)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: led.charge("cheap", 1000, 0), range(200)))
    assert led.spent() == pytest.approx(200 * 1000 / 1_000_000)


def test_charge_usd_records_a_labelled_spend(tmp_path):
    led = ledger(tmp_path, 10)
    led.charge_usd("train:Qwen/Qwen3-8B", 0.75)
    assert led.spent() == pytest.approx(0.75)
    assert json.loads((tmp_path / "spend.json").read_text())["by_model"]["train:Qwen/Qwen3-8B"]["usd"] == 0.75
