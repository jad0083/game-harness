"""A second, synthetic game (3 pillars, no actions) runs the strategy layer end to end: the
Strategist's schema, validation, the ranking, the frame and the off-frame check all follow its
pillars file, with no strategy-code change (spec 2026-09-26-game-pillars-design.md §5)."""

import shutil

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot.config import REPO, Settings
from pilot.events import EventLog
from pilot.game import FakeStellaris
from pilot.governor import Governor
from pilot.pillars import load_pillars
from pilot.strategy import Milestone, Pillar, Strategy, ranking, review_model, validate

SYNTH = """[strategy]
min_milestones_top = 1
metric_aliases = { planets = "colonies" }
instructions = "Grow tall: few cities, each great."

[metrics]
names = ["colonies", "pops", "techs_known"]
row_keys = { colonies = "planets" }

[pillars.science]
label = "Science"
description = "Research output and great scientists."
directive = "tech_rush"

[pillars.growth]
label = "Growth"
description = "New cities and population."
directive = "expand"

[pillars.culture]
label = "Culture"
description = "Great works and tourism."
"""


def briefing(date: str) -> dict:
    return {"date": date, "net": {"energy": 5.0}, "wars": [], "flags": []}


@pytest.fixture
def synth(tmp_path):
    corpus = tmp_path / "synth"
    corpus.mkdir()
    for f in ("pilot.md", "strategy.md", "directives.toml"):
        shutil.copy(REPO / "corpora/stellaris" / f, corpus / f)
    (corpus / "pillars.toml").write_text(SYNTH, encoding="utf-8")
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="synth", speed="fastest", decide_every_months=12, poll_s=0,
                 ask_human_timeout_s=0.05, fallback_model=None)      # tests never reach a real provider
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    return s, EventLog(s.runs_dir, "synth1", s.model), load_pillars(corpus)


def _strategist(schemas: list):
    def respond(messages, info: AgentInfo) -> ModelResponse:
        schemas.append(info.output_tools[0].parameters_json_schema)
        body = {"change": True, "assessment": "ok", "rules": [], "strategy": {
            "science": {"weight": 50, "stance": "research first", "goals": ["g"],
                        "milestones": [{"metric": "planets", "op": ">=", "target": 6, "by": "2230.01.01"}]},
            "growth": {"weight": 30, "stance": "settle", "goals": ["g"]},
            "culture": {"weight": 20, "stance": "later"},
            "focus": "tall", "reason": "start"}}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, body)])
    return FunctionModel(respond)


def _decider(prompts: list, choices: list[str]):
    n = {"i": 0}

    def respond(messages, info: AgentInfo) -> ModelResponse:
        prompts.append(" ".join(str(p.content) for m in messages for p in getattr(m, "parts", []) if hasattr(p, "content")))
        c = choices[min(n["i"], len(choices) - 1)]
        n["i"] += 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": c, "reason": f"test chose {c}"})])
    return FunctionModel(respond)


def test_a_synthetic_game_runs_review_and_decisions_on_its_own_pillars(synth):
    s, log, spec = synth
    schemas, prompts = [], []
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01")])
    g = Governor(s, game, log, model=_decider(prompts, ["keep", "defend"]), role_models={"strategy": _strategist(schemas)})
    g.run(max_decisions=2)

    out = next(d for d in schemas[0]["$defs"].values() if "focus" in d.get("properties", {}))
    assert set(out["properties"]) == {"science", "growth", "culture", "focus", "reason"}
    assert set(g.strategy.pillars) == {"science", "growth", "culture"}
    assert g.strategy.pillars["science"].milestones[0].metric == "colonies", "the synthetic game's alias"
    assert ranking(g.strategy, spec) == ["tech_rush", "expand"]
    assert "Directive pressure (weight x milestone need): tech_rush " in prompts[0] and "> expand " in prompts[0]
    traces = [e for e in log.recent if e["kind"] == "trace" and e.get("decision") == "defend"]
    assert traces and traces[-1].get("off_frame") is True, "defend is outside this game's ranking"
    assert g.review_requested and "off-frame" in g.review_requested
    assert not any(a[0] in ("pick_tech", "market_sync") for a in game.actions), "no actions declared"
    assert not any(e["kind"] == "strategy_action" for e in log.recent)


def test_the_synthetic_strategist_prompt_and_schema_carry_no_stellaris_pillars(synth):
    _s, _log, spec = synth
    from pilot.strategy import strategist_instructions
    text = strategist_instructions(spec)
    assert "- science (Science): Research output and great scientists. [ranks the directive tech_rush]" in text
    # "economy" itself also appears in the fixed, every-game species-guidance example ("industrious →
    # economy on minerals"; pinned by test_the_species_guidance_is_part_of_every_games_prompt), so the
    # no-Stellaris-pillars check looks for the game's own pillar/directive/action strings instead.
    assert "consolidate_economy" not in text and "Income, deficits, stockpiles and the market." not in text
    assert "prefer_techs" not in text and "Only " not in text
    assert "Grow tall: few cities, each great." in text
    schema = review_model(spec).model_json_schema()
    assert "prefer_techs" not in str(schema) and "market" not in str(schema)


def test_validation_follows_the_synthetic_spec(synth):
    _, _, spec = synth
    ms = [Milestone(metric="pops", op=">=", target=5, by="2230.01.01")]
    ok = Strategy(pillars={"science": Pillar(weight=50, stance="s", goals=["g"], milestones=ms),
                           "growth": Pillar(weight=30, stance="s"), "culture": Pillar(weight=20, stance="s")}, focus="f")
    assert validate(ok, spec, previous=None, tech_ids=set(), idle=set(), income={}) == []
    stellaris_shaped = Strategy(pillars={"economy": Pillar(weight=100, stance="s", milestones=ms)}, focus="f")
    errs = " | ".join(validate(stellaris_shaped, spec, previous=None, tech_ids=set(), idle=set(), income={}))
    assert "unknown pillar 'economy'" in errs and "missing pillar science" in errs
    bad = Strategy(pillars={**ok.pillars, "culture": Pillar(
        weight=25, stance="s", milestones=[Milestone(metric="systems", op=">=", target=1, by="2230.01.01")],
        prefer_techs=["x"])}, focus="f")
    errs = " | ".join(validate(bad, spec, previous=None, tech_ids=set(), idle=set(), income={}))
    assert "weights must sum to 100 (got 105)" in errs
    assert "culture: unknown metric 'systems'" in errs
    assert "culture: prefer_techs is not an action in this game" in errs
    no_ms = Strategy(pillars={**ok.pillars, "science": Pillar(weight=50, stance="s")}, focus="f")
    assert "science: priority 1 is in the top 1 and needs at least one milestone" in \
        validate(no_ms, spec, previous=None, tech_ids=set(), idle=set(), income={})
