import pytest

from onebar.check.checker import check
from onebar.dataset import llm, paraphrase, teacher
from onebar.facts.model import Fact, FactSet
from onebar.model.client import ModelError
from onebar.model.prompt import STOP


# ---- Sampler -------------------------------------------------------------------------------------------------

class Choice:
    def __init__(self, text):
        self.text = text


class Resp:
    def __init__(self, *texts):
        self.choices = [Choice(t) for t in texts]


class StatusError(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status_code = status


class Completions:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def create(self, **kw):
        self.calls.append(kw)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


class Client:
    def __init__(self, *outcomes):
        self.completions = Completions(*outcomes)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def test_sample_returns_n_texts_and_passes_the_stop_and_temperature():
    # the endpoint returns one completion per call whatever n says, so three are drawn with three calls
    c = Client(Resp("a"), Resp("b"), Resp("c"))
    out = llm.Sampler("m", client=c).sample("P", n=3, temperature=0.8, max_tokens=50)
    assert out == ["a", "b", "c"] and len(c.completions.calls) == 3
    kw = c.completions.calls[0]
    assert (kw["model"], kw["temperature"], kw["max_tokens"], kw["stop"]) == ("m", 0.8, 50, [STOP])


def test_a_client_that_does_return_n_is_not_called_again():
    c = Client(Resp("a", "b", "c"))
    assert llm.Sampler("m", client=c).sample("P", n=3) == ["a", "b", "c"] and len(c.completions.calls) == 1


class ChatChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class ChatCompletions:
    def __init__(self, *contents):
        self.contents, self.calls = contents, []

    def create(self, **kw):
        self.calls.append(kw)
        return type("R", (), {"choices": [ChatChoice(c) for c in self.contents]})()


def test_message_prompts_use_the_chat_endpoint_with_room_for_reasoning():
    chat = ChatCompletions(None)
    client = type("C", (), {"chat": type("X", (), {"completions": chat})()})()
    msgs = [{"role": "user", "content": "hi"}]
    out = llm.Sampler("gpt-oss", client=client).sample(msgs, n=1, max_tokens=120)
    assert out == [""]  # a null content (reasoning ate the budget) becomes an empty string
    kw = chat.calls[0]
    assert kw["messages"] == msgs and kw["reasoning_effort"] == "low"
    assert kw["max_tokens"] == llm.CHAT_MIN_TOKENS


def test_rate_limits_and_server_errors_are_retried():
    c = Client(StatusError(429), StatusError(503), Resp("ok"))
    assert llm.Sampler("m", client=c).sample("P") == ["ok"]
    assert len(c.completions.calls) == 3


def test_client_errors_are_not_retried():
    c = Client(StatusError(400), Resp("never"))
    with pytest.raises(ModelError, match="StatusError"):
        llm.Sampler("m", client=c).sample("P")
    assert len(c.completions.calls) == 1


def test_gives_up_after_the_retry_budget():
    c = Client(*[StatusError(429)] * 3)
    with pytest.raises(ModelError):
        llm.Sampler("m", client=c, retries=3).sample("P")
    assert len(c.completions.calls) == 3


def test_missing_key_is_a_model_error(monkeypatch):
    monkeypatch.delenv("TINKER_API_KEY", raising=False)
    with pytest.raises(ModelError, match="TINKER_API_KEY"):
        llm.Sampler("m")


def test_parallel_map_keeps_order_and_isolates_failures():
    def f(x):
        if x == 3:
            raise ValueError("boom")
        return x * 2

    out = llm.parallel_map(f, range(6), workers=4)
    assert out[:3] == [0, 2, 4] and isinstance(out[3], ValueError) and out[4:] == [8, 10]


# ---- paraphrase ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "seed, cand, want",
    [
        ("storm before 3pm?", "storm coming before 3pm", "storm coming before 3pm"),
        ("storm before 3pm?", '"storm coming before 3pm"', "storm coming before 3pm"),
        ("storm before 3pm?", "storm coming before 3pm?\nextra line", "storm coming before 3pm?"),
        ("storm before 3pm?", "storm coming before 4pm", None),  # changed number
        ("storm before 3pm?", "storm coming?", None),  # dropped number
        ("storm before 3pm?", "storm coming before 3pm and 5 pm", None),  # added number
        ("storm before 3pm?", "any storm b4 3pm", None),  # a digit glued into a word reads as a number
        ("storm before 3pm?", "3pm storm?", None),  # same number, but parse_target no longer finds a target time
        ("storm before 3pm?", "storm until 3pm?", "storm until 3pm?"),  # a different preposition reads the same time
        ("how cold will it get?", "how cold at 9?", None),  # added number
        ("how cold will it get?", "how windy will it get?", None),  # intent changed
        ("how cold will it get?", "how cold will it get? ❄", None),  # non-ASCII
        ("how cold will it get?", "", None),
        ("how cold will it get?", "   ", None),
        ("how cold will it get?", "x" * 101, None),
    ],
)
def test_paraphrase_acceptance(seed, cand, want):
    assert paraphrase.accept(seed, cand) == want


def test_paraphrase_prompt_is_chat_formatted_with_one_open_assistant_turn():
    p = paraphrase.prompt("storm before 3pm?")
    assert p.count("<|im_start|>assistant") == 4  # three shots plus the open turn
    assert p.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert p.count("<think>") == 1
    assert "storm before 3pm?" in p.split("<|im_start|>user")[-1]


def test_every_paraphrase_shot_would_itself_be_accepted():
    for src, dst in paraphrase.SHOTS:
        assert paraphrase.accept(src, dst) == dst, (src, dst)


# ---- teacher -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("question, pairs, reply", teacher.EXAMPLES)
def test_every_teacher_example_passes_the_checker_and_is_natural(question, pairs, reply):
    facts = teacher.example_facts(pairs)
    result = check(reply, facts, question)
    assert result.passed, result.reasons
    assert result.septets <= 160
    assert teacher.natural(reply)


def test_teacher_prompt_ends_in_one_open_think_turn_and_holds_the_real_facts():
    facts = FactSet([Fact("now", "10:20"), Fact("gust_max", "77km/h")])
    p = teacher.prompt(facts, "wind?")
    assert p.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    assert p.count("<think>") == 1
    assert p.count("<|im_start|>assistant") == len(teacher.EXAMPLES) + 1
    assert "strongest wind gust in the next hours: 77km/h" in p.split("<|im_start|>user")[-1]


@pytest.mark.parametrize(
    "text, ok",
    [
        ("Gusts up to 62km/h around 19:00.", True),
        ("strongest wind gust in the next hours: 62km/h", False),
        ("Time now: 10:20. storm_first 14:00", False),
        ("Storm", False),  # too short
        ("Line one.\nLine two.", False),
        # echoes copied from the Phase 2 base-model run
        ("Yes. highest chance of rain in the next hours: 100% first rain hour: 17:00", False),
        ("Latest turn-around time: 15:00 thunderstorm: no storm", False),
        ("next sunset: 18:59", False),
        ("No rain. First thunderstorm hour: 13:00.", False),
        # ordinary words that happen to be labels stay allowed
        ("Rain from 17:00, so pack a shell. Next sunset is 18:59.", True),
    ],
)
def test_natural(text, ok):
    assert teacher.natural(text) is ok


FACTS = FactSet([Fact("now", "10:20"), Fact("gust_max", "62km/h"), Fact("storm_none", "no storm")])


def test_pick_takes_the_shortest_passing_natural_candidate():
    c = teacher.pick(
        ["Gusts up to 62km/h, no storm expected today.", "No storm. Gusts 62km/h.", "Gusts 99km/h.", "no storm. gusts: x"],
        FACTS, "is it safe to keep going?",
    )
    assert c.text == "No storm. Gusts 62km/h."
    assert c.n_candidates == 4 and c.n_passed == 2


def test_pick_returns_none_when_nothing_qualifies():
    assert teacher.pick(["Gusts 99km/h.", "", "strongest wind gust in the next hours: 62km/h"], FACTS, "wind?") is None


def test_pick_dedupes_and_unquotes():
    c = teacher.pick(['"No storm. Gusts 62km/h."', "No storm. Gusts 62km/h."], FACTS, "wind?")
    assert c.text == "No storm. Gusts 62km/h." and c.n_candidates == 1


def test_pick_never_returns_a_reply_the_checker_rejects():
    cands = ["No storm. Gusts 62km/h.", "Storm from 14:00.", "Gusts 62mph.", "A" * 200]
    c = teacher.pick(cands, FACTS, "wind?")
    assert check(c.text, FACTS, "wind?").passed
