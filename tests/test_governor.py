import shutil

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.config import REPO, Settings
from pilot.events import EventLog
from pilot.game import FakeStellaris
from pilot.governor import Governor, current_directive, months, urgent_changes


def briefing(date: str, net: dict | None = None, wars: list | None = None) -> dict:
    return {"date": date, "net": net or {"energy": 5.0, "food": 3.0}, "wars": wars or [], "flags": []}


def decisions(*choices: str, consult_first: bool = False):
    """A model that returns the given directives in order (one per decision)."""
    calls = {"n": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if consult_first and step == 0 and calls["n"] == 0:
            return ModelResponse(parts=[ToolCallPart("consult", {"query": "diplomatic stance"})])
        choice = choices[min(calls["n"], len(choices) - 1)]
        calls["n"] += 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                 {"directive": choice, "reason": f"test chose {choice}"})])

    return FunctionModel(respond)


@pytest.fixture
def setup(tmp_path):
    corpus = tmp_path / "stellaris"
    corpus.mkdir()
    for f in ("manifest.toml", "pilot.md", "strategy.md", "directives.toml"):
        shutil.copy(REPO / "corpora/stellaris" / f, corpus / f)
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="stellaris", speed="fastest", decide_every_months=12, poll_s=0,
                 ask_human_timeout_s=0.05)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "run1", s.model)


def test_helpers():
    assert months("2201.01.01") - months("2200.01.01") == 12
    assert current_directive({"flags": ["x", "governor_directive_defend"]}) == "defend"
    assert current_directive({"flags": []}) is None
    before = briefing("2200.01.01", net={"food": 2.0, "energy": 1.0})
    now = briefing("2200.02.01", net={"food": -1.5, "energy": 1.0}, wars=[{"name": "Border War", "attacker": False}])
    reasons = urgent_changes(before, now)
    assert any("new war: Border War (we are defender)" in r for r in reasons)
    assert any("food net turned negative" in r for r in reasons)
    assert urgent_changes(now, now) == []   # an existing deficit or war does not re-trigger


def test_governor_decides_on_schedule_and_pauses_while_deciding(setup):
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.06.01"), briefing("2201.01.01")])
    gov = Governor(s, game, log, model=decisions("expand", "keep", consult_first=True))
    gov.run(max_decisions=2)

    acts = [a for a in game.actions if a[0] != "corpus"]
    assert acts[:3] == [("paused", True), ("speed", "fastest"), ("directive", "expand")]
    # resumed after the first decision, paused again at the scheduled date (12 months later)
    assert acts[3] == ("paused", False) and acts[4] == ("paused", True)
    assert ("directive", "keep") not in acts and acts.count(("directive", "expand")) == 1
    assert game.paused is True, "left paused at the end"
    assert log.state.episodes == 2 and log.state.game_date == "2201.01.01"
    eps = [e for e in log.recent if e["kind"] == "episode"]
    assert eps[0]["situation"] == "start of run" and eps[1]["situation"].startswith("scheduled")
    assert ("corpus", "corpus_search", {"query": "diplomatic stance", "limit": 5}) in game.actions
    assert "expand (applied)" in (s.journal).read_text()


def test_governor_decides_early_on_a_new_war(setup):
    s, log = setup
    war = [{"name": "Invasion of Sol", "attacker": False}]
    game = FakeStellaris([briefing("2200.01.01"), briefing("2200.03.01", wars=war)])
    Governor(s, game, log, model=decisions("expand", "defend")).run(max_decisions=2)
    assert [a for a in game.actions if a[0] == "directive"] == [("directive", "expand"), ("directive", "defend")]
    ep = [e for e in log.recent if e["kind"] == "episode"][1]
    assert ep["situation"].startswith("urgent: new war: Invasion of Sol")


def test_prepare_war_needs_a_human_yes(setup):
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    Governor(s, game, log, model=decisions("prepare_war")).run(max_decisions=1)
    assert ("directive", "prepare_war") not in game.actions
    assert any(e["kind"] == "question" for e in log.recent)
    assert "needs a human yes" in log.state.last_decision
