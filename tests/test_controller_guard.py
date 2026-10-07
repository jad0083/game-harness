"""GalCiv episodes on the model guard (docs/design/2026-10-02-model-guard-design.md, ruling 18): an episode
whose model is overloaded mid-run continues on the fallback model without repeating its actions."""

from __future__ import annotations

from conftest import journal_text
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_pilot import FakeGame, corpus  # noqa: F401

from pilot.config import Settings
from pilot.controller import Pilot
from pilot.events import EventLog
from pilot.store import open_store

E503 = ModelHTTPError(503, "gemini-3.8-flash", {"error": {"code": 503, "status": "UNAVAILABLE"}})


def note_then_503():
    def respond(messages, info):
        if sum(isinstance(m, ModelResponse) for m in messages) == 0:
            return ModelResponse(parts=[ToolCallPart("note", {"text": "Saw the event", "game_date": "Jul 2333"})])
        raise E503
    return FunctionModel(respond, model_name="gemini-3.8-flash")


def finisher():
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "situation": "Event", "decision": "Done", "game_date": "", "resolved": True})])
    return FunctionModel(respond, model_name="gemini-3.1-pro-preview")


def make(corpus, tmp_path, **kw):  # noqa: F811
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs",
                 game="x", fallback_model=None, **kw)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "run1", s.model)


def test_an_episode_continues_on_the_fallback_and_notes_once(corpus, tmp_path):  # noqa: F811
    s, log = make(corpus, tmp_path)
    pilot = Pilot(s, FakeGame([]), log, model=note_then_503(), fallback=finisher())
    pilot._episode("a dialog is up", None)
    assert journal_text(s.runs_dir).count("Saw the event") == 1, "the note tool ran once"
    fb = [e for e in log.recent if e["kind"] == "model_fallback"][-1]
    assert fb["role"] == "episodes" and fb["failure"] == "overloaded" and fb["request"] == 2
    assert pilot.health.status("google:gemini-3.8-flash") == "open"
    assert any(e["kind"] == "model_breaker" for e in log.recent)
    assert log.state.info["model_health"]["models"]["google:gemini-3.8-flash"]["state"] == "open"


def test_each_episode_publishes_todays_counts(corpus, tmp_path):  # noqa: F811
    """The pool editor's "N requests today" follows GalCiv too: published after every episode's run,
    whether it answered or failed, not only on a breaker change."""
    s, log = make(corpus, tmp_path, pool_max_wait_s=0)
    pilot = Pilot(s, FakeGame([]), log, model=finisher())
    pilot._episode("a dialog is up", None)
    assert log.state.info["model_health"]["models"]["google:gemini-3.8-flash"]["today"] == 1
    assert not any(e["kind"] == "model_breaker" for e in log.recent), "no breaker change published it"

    def rejected(messages, info):
        raise ModelHTTPError(400, "gemini-3.8-flash", "bad request")    # a rejected request opens nothing
    pilot = Pilot(s, FakeGame([]), log, model=FunctionModel(rejected, model_name="gemini-3.8-flash"))
    pilot._episode("a dialog is up", None)
    assert any(e["kind"] == "episode_error" for e in log.recent)
    assert log.state.info["model_health"]["models"]["google:gemini-3.8-flash"]["today"] == 2


def test_a_stop_ends_the_wait_for_an_episodes_models(corpus, tmp_path, monkeypatch):  # noqa: F811
    """Pool-wait ruling 3 for GalCiv: the episode's pool reads the pilot's stop flag."""
    from pilot import modelguard as G
    s, log = make(corpus, tmp_path)

    def down(messages, info):
        raise E503
    pilot = Pilot(s, FakeGame([]), log, model=FunctionModel(down, model_name="gemini-3.8-flash"))
    waited = []

    async def sleep(seconds):
        if pilot.health.status("google:gemini-3.8-flash") == "open":
            waited.append(seconds)
            pilot.stop()
    monkeypatch.setattr(G, "_sleep", sleep)
    pilot._episode("a dialog is up", None)
    ex = [e for e in log.recent if e["kind"] == "pool_exhausted"][-1]
    assert ex["role"] == "episodes" and ex["causes"][-1] == {"model": "-", "error": "stopped while waiting"}
    assert sum(waited) <= G.POOL_STOP_STEP_S and any(e["kind"] == "episode_error" for e in log.recent)
    assert [e["role"] for e in log.recent if e["kind"] == "model_wait"] == ["episodes"]


def test_changing_the_model_clears_its_broken_mark(corpus, tmp_path):  # noqa: F811
    """Plan ruling P2 for GalCiv: a pool rebuild lets the new pool's broken models be tried again."""
    from pilot.modelguard import BROKEN, Failure
    s, log = make(corpus, tmp_path)
    pilot = Pilot(s, FakeGame([]), log, model=finisher())
    pilot.health.failed("google:gemini-3.7-flash", Failure(BROKEN, 404))
    pilot.health.failed("google:gemini-3.1-pro-preview", Failure(BROKEN, 404))
    pilot.set_model("google:gemini-3.7-flash")
    assert pilot.health.status("google:gemini-3.7-flash") == "closed"
    assert pilot.health.status("google:gemini-3.1-pro-preview") == "broken", "not in the new pool"
    cleared = [e for e in log.recent if e["kind"] == "model_breaker"][-1]
    assert (cleared["model"], cleared["state"], cleared["reason"]) == ("google:gemini-3.7-flash", "closed", "cleared")
    published = log.state.info["model_health"]["models"]
    assert "google:gemini-3.7-flash" not in published, "no breaker and no request today: nothing to show"
    assert published["google:gemini-3.1-pro-preview"]["state"] == "broken"


def test_without_the_guard_the_episode_replays_as_before(corpus, tmp_path):  # noqa: F811
    s, log = make(corpus, tmp_path, model_guard=False, retry_delays=(0,))
    pilot = Pilot(s, FakeGame([]), log, model=note_then_503(), fallback=finisher())
    pilot._episode("a dialog is up", None)
    assert journal_text(s.runs_dir).count("Saw the event") == 2, "the whole run was retried"
    assert not any(e["kind"] == "model_breaker" for e in log.recent)
    assert pilot.pool is None and "model_health" not in log.state.info
    assert open_store(s.runs_dir).query("SELECT * FROM model_usage") == []
    pilot.set_model("google:gemini-3.7-flash")
    assert pilot.pool is None and "model_health" not in log.state.info, "a model change publishes nothing either"
