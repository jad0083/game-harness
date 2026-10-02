"""GalCiv episodes on the model guard (docs/design/2026-10-02-model-guard-design.md, ruling 18): an episode
whose model is overloaded mid-run continues on the fallback model without repeating its actions."""

from __future__ import annotations

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_pilot import FakeGame, corpus  # noqa: F401

from pilot.config import Settings
from pilot.controller import Pilot
from pilot.events import EventLog

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
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="x", fallback_model=None, **kw)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "run1", s.model)


def test_an_episode_continues_on_the_fallback_and_notes_once(corpus, tmp_path):  # noqa: F811
    s, log = make(corpus, tmp_path)
    pilot = Pilot(s, FakeGame([]), log, model=note_then_503(), fallback=finisher())
    pilot._episode("a dialog is up", None)
    assert (tmp_path / "journal.md").read_text().count("Saw the event") == 1, "the note tool ran once"
    fb = [e for e in log.recent if e["kind"] == "model_fallback"][-1]
    assert fb["role"] == "episodes" and fb["failure"] == "overloaded" and fb["request"] == 2
    assert pilot.health.status("google:gemini-3.8-flash") == "open"
    assert any(e["kind"] == "model_breaker" for e in log.recent)
    assert log.state.info["model_health"]["models"]["google:gemini-3.8-flash"]["state"] == "open"


def test_without_the_guard_the_episode_replays_as_before(corpus, tmp_path):  # noqa: F811
    s, log = make(corpus, tmp_path, model_guard=False, retry_delays=(0,))
    pilot = Pilot(s, FakeGame([]), log, model=note_then_503(), fallback=finisher())
    pilot._episode("a dialog is up", None)
    assert (tmp_path / "journal.md").read_text().count("Saw the event") == 2, "the whole run was retried"
    assert not any(e["kind"] == "model_breaker" for e in log.recent)
    assert pilot.pool is None and "model_health" not in log.state.info
    assert not (tmp_path / "runs" / "model-usage.json").exists()
