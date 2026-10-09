import pytest

from onebar.model import client
from onebar.model.client import ModelError, TinkerDraft, clean


@pytest.mark.parametrize(
    "raw, want",
    [
        ("  Storm 14:40.  ", "Storm 14:40."),
        ('"Storm 14:40."', "Storm 14:40."),
        ("'Storm 14:40.'", "Storm 14:40."),
        ("<think>hmm</think>\nStorm 14:40.", "Storm 14:40."),
        ("<think>\n\n</think>\n\nStorm 14:40.", "Storm 14:40."),
        ('He said "go"', 'He said "go"'),  # inner quotes stay
        ("", ""),
        ('"', '"'),
    ],
)
def test_clean(raw, want):
    assert clean(raw) == want


def test_missing_key_raises_model_error(monkeypatch):
    monkeypatch.delenv("TINKER_API_KEY", raising=False)
    with pytest.raises(ModelError, match="TINKER_API_KEY"):
        TinkerDraft()


class _Choice:
    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, texts):
        self.choices = [_Choice(t) for t in texts]


class _Completions:
    def __init__(self, outcome):
        self.outcome, self.kwargs = outcome, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _draft(outcome, monkeypatch, model_env=None):
    monkeypatch.delenv("ONEBAR_MODEL", raising=False)
    if model_env:
        monkeypatch.setenv("ONEBAR_MODEL", model_env)
    d = TinkerDraft(api_key="k")
    d._client.completions = _Completions(outcome)
    return d


def test_call_passes_stop_temperature_and_model(monkeypatch):
    d = _draft(_Resp(["Storm 14:40.<"]), monkeypatch)
    assert d("P") == "Storm 14:40.<"
    kw = d._client.completions.kwargs
    assert kw["model"] == client.DEFAULT_MODEL
    assert kw["prompt"] == "P" and kw["stop"] == ["<|im_end|>"] and kw["temperature"] == 0.0


def test_token_usage_accumulates_and_tolerates_a_missing_usage_field(monkeypatch):
    usage = type("U", (), {"prompt_tokens": 300, "completion_tokens": 25})()
    r1 = _Resp(["a"])
    r1.usage = usage
    d = _draft(r1, monkeypatch)
    d("P")
    d._client.completions = _Completions(_Resp(["b"]))  # no usage attribute at all
    d("P")
    assert (d.calls, d.prompt_tokens, d.completion_tokens) == (2, 300, 25)


def test_model_name_comes_from_env(monkeypatch):
    d = _draft(_Resp(["x"]), monkeypatch, model_env="tinker://abc/sampler_weights/000001")
    assert d.model == "tinker://abc/sampler_weights/000001"


def test_sdk_errors_become_model_error(monkeypatch):
    d = _draft(TimeoutError("slow"), monkeypatch)
    with pytest.raises(ModelError, match="TimeoutError"):
        d("P")


@pytest.mark.parametrize("texts", [[], [""], ["   "], ["<think>x</think>"]])
def test_empty_completion_is_a_model_error(texts, monkeypatch):
    d = _draft(_Resp(texts), monkeypatch)
    with pytest.raises(ModelError, match="empty"):
        d("P")
