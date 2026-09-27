"""What the governors publish for the dashboard (docs/design/2026-09-27-dashboard-v2-design.md): the
fields the page reads from /status and the events it turns into sentences."""

from __future__ import annotations

import time
import urllib.error
from dataclasses import replace

from test_governor import _Clock, _flaky_pause, _run_bg, _strategist, _wait, briefing, decisions, setup  # noqa: F401

from pilot.game import FakeStellaris
from pilot.governor import Governor
from pilot.view import CATEGORIES


def test_a_skipped_review_says_when_the_next_one_may_run(setup):  # noqa: F811
    """Ruling 16: skipped reviews are listed with the next eligible date in game units."""
    s, log = setup
    s2 = replace(s, decide_every_months=1, retro_every=0)
    s2.__class__ = s.__class__
    game = FakeStellaris([briefing(f"2200.{i:02d}.01") for i in range(1, 9)])
    choices = ("tech_rush", "expand", "diplomacy_first", "tech_rush", "expand", "diplomacy_first", "tech_rush", "expand")
    g = Governor(s2, game, log, model=decisions(*choices), role_models={"strategy": _strategist([])})
    g.run(max_decisions=8)
    skips = [e for e in log.recent if e["kind"] == "strategy_review_skipped"]
    assert skips
    for e in skips:
        assert e["date"].startswith("2200.") and e["next_after"] == g._last_event_review_month + 12


# ---- needs you: info.attention with a category per call site (ruling 7) ------------------------------

def attention(log) -> dict | None:
    return log.state.info.get("attention")


def test_a_control_failure_publishes_its_reason_category_and_date(setup):  # noqa: F811
    s, log = setup

    class Stuck(FakeStellaris):
        def set_paused(self, paused):
            if paused is False:
                raise RuntimeError("Stellaris is not in the foreground")
            return super().set_paused(paused)

    gov = Governor(s, Stuck([briefing("2200.01.01")]), log, model=decisions("keep"))
    gov.recover_every_s = 0
    t = _run_bg(gov)
    assert _wait(lambda: log.state.status == "needs_attention")
    a = attention(log)
    assert a["category"] == "control_failed" and "not in the foreground" in a["reason"]
    assert a["auto_recover"] is False and a["date"] == "2200.01.01" and abs(a["since"] - time.time()) < 5
    assert next(e for e in log.recent if e["kind"] == "needs_attention")["category"] == "control_failed"
    gov.stop()
    t.join(5)


def test_resume_clears_the_attention(setup):  # noqa: F811
    s, log = setup
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    gov._needs_attention("a popup holds the game", category="screen")
    assert attention(log)["category"] == "screen" and log.state.status == "needs_attention"
    gov.resume()
    assert attention(log) is None and log.state.status == "playing"


def test_a_transient_failure_says_it_retries_by_itself_and_counts_the_probes(setup, monkeypatch):  # noqa: F811
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01"), briefing("2201.01.01"), briefing("2202.01.01"), briefing("2203.01.01")])
    g = Governor(s, game, log, model=decisions("defend", "keep"))
    g.recover_every_s = 0
    flaky, _ = _flaky_pause(game, log, urllib.error.URLError("timed out"), while_attention=2)
    seen: list[dict] = []

    def watch(p):
        if attention(log):
            seen.append(dict(attention(log)))
        return flaky(p)
    monkeypatch.setattr(game, "set_paused", watch)
    g.run(max_decisions=2)
    assert seen and seen[0]["category"] == "unreachable" and seen[0]["auto_recover"] is True
    assert seen[0]["next_probe_at"] >= seen[0]["since"] and seen[-1]["probes"] >= 1
    assert attention(log) is None, "recovered by itself: the card goes"


def test_a_stall_and_a_changed_game_have_their_categories(setup):  # noqa: F811
    s, log = setup
    game = FakeStellaris([briefing("2200.01.01")])
    gov = Governor(s, game, log, model=decisions("keep"))
    gov._clock = _Clock(game, step=60)
    gov._run_until_next_decision(briefing("2200.01.01"))
    assert attention(log)["category"] == "stall"

    s2, log2 = s, type(log)(s.runs_dir, "run2", s.model)
    other = {**briefing("2200.02.01"), "source": "save games/other_2/autosave_2200.02.01.sav"}
    gov2 = Governor(s2, FakeStellaris([other]), log2, model=decisions("keep"))
    gov2._folder = "governed_1"
    gov2._run_until_next_decision(briefing("2200.01.01"))
    assert attention(log2)["category"] == "game_changed"


def test_unread_saves_flag_unreachable_and_clear_by_themselves(setup):  # noqa: F811
    s, log = setup
    s.decide_every_months = 3

    class Away(FakeStellaris):
        fails = 8

        def briefing(self):
            if self.fails:
                self.fails -= 1
                raise ConnectionError("agent away")
            return super().briefing()

    game = Away([briefing(f"2200.{m:02d}.01") for m in range(1, 8)])
    gov = Governor(s, game, log, model=decisions("keep"))
    seen: list[dict] = []
    real = log.emit

    def emit(kind, *a, **kw):
        ev = real(kind, *a, **kw)
        if kind == "needs_attention":
            seen.append(dict(attention(log) or {}))
        return ev
    log.emit = emit
    gov._clock = _Clock(game, step=60)
    gov._run_until_next_decision(briefing("2200.01.01"))
    assert seen and seen[0]["category"] == "unreachable" and seen[0]["auto_recover"] is True
    assert attention(log) is None, "the flag cleared once a save read again"


def test_the_attention_lists_the_errors_behind_the_stop_cut_to_their_cause(setup):  # noqa: F811
    s, log = setup
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    log.emit("briefing_error", error="Error: Failed /tuner/lua\n\nCaused by:\n    0: error sending request\n"
                                     "    1: operation timed out")
    log.emit("episode_error", error="ModelHTTPError: status_code: 503, model_name: m, body: high demand")
    gov._needs_attention("could not start", category="control_failed")
    a = attention(log)
    assert a["errors"] == ["the game's tuner did not answer (timed out)", "overloaded (503)"]
    assert len(a["raw"]) == 2 and "operation timed out" in a["raw"][0]


def test_every_category_a_governor_sets_is_a_known_one():
    """The recovery steps in dashboard.toml are looked up by these categories (tests/test_dashboard_view.py
    checks the files against CATEGORIES): every `category` given to a needs-attention call or an
    attention object, and every stop class's `category`, is one of them, and each one is used."""
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "pilot"
    used: set[str] = set()

    def strings(node):
        return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    for f in ("governor.py", "civ6_governor.py", "controller.py"):
        for node in ast.walk(ast.parse((src / f).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
                    "_needs_attention", "attention"):
                for kw in node.keywords:
                    if kw.arg == "category":
                        used |= strings(kw.value)
                if getattr(node.func, "id", "") == "attention" and len(node.args) > 1:
                    used |= strings(node.args[1])
            if isinstance(node, ast.ClassDef):
                for st in node.body:
                    if isinstance(st, ast.Assign) and any(getattr(t, "id", "") == "category" for t in st.targets):
                        used |= strings(st.value)
    assert used <= set(CATEGORIES), used - set(CATEGORIES)
    assert used == set(CATEGORIES), set(CATEGORIES) - used


# ---- deciding: progress while the model works, and who answered (rulings 6, 9, 11) -----------------------

def test_deciding_shows_the_attempt_and_the_answer_names_the_fallback(setup):  # noqa: F811
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    s, log = setup
    s = replace(s, retry_delays=(0,))
    s.__class__ = setup[0].__class__
    during: list[dict] = []

    def overloaded(messages, info):
        raise ModelHTTPError(503, "gemini-3.8-flash", "high demand")

    def answer(messages, info):
        if "change" in info.output_tools[0].parameters_json_schema.get("properties", {}):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"change": False, "assessment": "n/a", "rules": []})])
        during.append(dict(log.state.info.get("deciding") or {}))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"directive": "expand", "reason": "r"})])

    fallback = FunctionModel(answer, model_name="gemini-3.1-pro-preview")
    Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=FunctionModel(overloaded), fallback=fallback,
             role_models={"strategy": _strategist([])}).run(max_decisions=1)
    d = during[-1]
    assert d["trigger"] == "start of run" and d["attempt"] == 2 and d["max_attempts"] == 2
    assert d["model"] == "gemini-3.1-pro-preview" and d["retry_at"] is None
    assert d["after"] == [{"model": "google:gemini-3.8-flash", "error": "overloaded (503)"}]
    assert "deciding" not in log.state.info
    ans = log.state.info["answered"]
    assert ans["model"] == "gemini-3.1-pro-preview" and ans["fallback"] is True


def test_a_retry_wait_says_when_the_next_try_is(setup):  # noqa: F811
    s, log = setup
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("keep"))
    gov._status("deciding", trigger="scheduled (12 months)")
    assert log.state.info["deciding"]["trigger"] == "scheduled (12 months)"

    class E(Exception):
        status_code, model_name = 503, "gemini-3.8-flash"
    gov._on_retry(E(), 12, 1)
    d = log.state.info["deciding"]
    assert 11 <= d["retry_at"] - time.time() <= 13 and d["retries"] == 1
    gov._status("playing")
    assert "deciding" not in log.state.info


def test_a_question_carries_its_deadline_and_what_silence_means(setup):  # noqa: F811
    s, log = setup
    gov = Governor(s, FakeStellaris([briefing("2200.01.01")]), log, model=decisions("prepare_war"))
    seen = {}
    real = gov.human.ask

    def ask(q, timeout):
        seen.update(deadline=log.state.question_deadline, default=log.state.default_if_silent, q=log.state.pending_question)
        return real(q, timeout)
    gov.human.ask = ask
    gov.run(max_decisions=1)
    assert seen["q"] and seen["default"] == "no" and seen["deadline"] > time.time() - 5
    assert log.state.question_deadline == 0 and log.state.default_if_silent == ""
