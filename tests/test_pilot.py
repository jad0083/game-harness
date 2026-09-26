import io
import json
import shutil
import tomllib

import pytest
from PIL import Image, ImageDraw
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pilot import coords
from pilot.agent import IMAGE_STUB, trim_images
from pilot.config import REPO, Settings
from pilot.controller import Pilot
from pilot.events import EventLog
from pilot.game import FakeGame, TurnReport, classify_report
from pilot.learning import Journal, LearnedStore, LearningRejected, ScreenAction


def jpeg(title: str | None, seed: int = 0) -> bytes:
    """A 1568x882 frame: a noisy 'map', optionally with a dialog title box."""
    im = Image.new("RGB", (1568, 882), (15, 20, 40))
    d = ImageDraw.Draw(im)
    for i in range(0, 1568, 37):
        d.line([(i, 0), ((i * 7 + seed * 53) % 1568, 882)], fill=(40 + (i + seed * 31) % 120, 60, 90))
    if title:
        d.rectangle([576, 290, 992, 330], fill=(0, 0, 0))
        d.text((700, 302), title, fill=(240, 240, 240))
        d.rectangle([815, 510, 975, 540], fill=(30, 60, 140))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@pytest.fixture
def corpus(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    for f in ("manifest.toml", "pilot.md", "strategy.md"):
        shutil.copy(REPO / "corpora/galciv4" / f, d / f)
    return d


# -- coordinates ---------------------------------------------------------------------------------

def test_coordinate_conventions():
    assert coords.to_image(500, 500, "norm1000") == (784, 441)
    assert coords.to_image(1000, 1000, "norm1000") == (1567, 881), "clamped inside the frame"
    assert coords.to_image(480, 618, "pixels") == (480, 618)
    assert Settings(model="google:gemini-3.8-flash").coord_space == "norm1000"
    assert Settings(model="openai:gpt-5").coord_space == "pixels"
    assert Settings(model="openai:gpt-5", coords="norm1000").coord_space == "norm1000"
    with pytest.raises(ValueError):
        coords.to_image(1, 1, "inches")


def test_gemini_image_metadata_matches_the_sdk_type():
    from google.genai import types

    from pilot.agent import image_metadata

    meta = image_metadata(Settings(model="google:gemini-3.8-flash", image_detail="medium"))
    types.PartMediaResolution.model_validate(meta["media_resolution"])   # raises if the shape is wrong
    assert image_metadata(Settings(model="openai:gpt-5")) is None


def test_gemini_thinking_config_matches_the_sdk_type():
    from google.genai import types

    from pilot.agent import model_settings

    cfg = model_settings(Settings(model="google:gemini-3.8-flash", thinking="low"))["google_thinking_config"]
    assert types.ThinkingConfig.model_validate(cfg).include_thoughts is True


def test_autopilot_report_classification():
    assert classify_report("Advanced 2 turn(s), then stopped at turn 3: a dialog is up (HUD dimmed") == "dialog"
    assert classify_report("Advanced 0 turn(s), then stopped at turn 1: turn indicator unchanged ... blocking end-turn") == "blocked"
    assert classify_report("Advanced 0 turn(s), then stopped at turn 1: the game is still processing the turn") == "processing"
    assert classify_report("Advanced 20 turn(s); each verified by the date readout changing.") == "limit"


# -- learning store ------------------------------------------------------------------------------

def test_learn_screen_validates_distinctness_and_writes_overlay(corpus):
    store = LearnedStore(corpus, "test-model", "run1")
    shown = jpeg("Colonize Planet")
    with pytest.raises(LearningRejected, match="no frames without"):
        store.add_screen("colony_prompt", shown, (576, 290, 992, 330), ScreenAction(click=(895, 525)), "d", "e")
    store.remember_frame(jpeg(None, seed=1))
    store.remember_frame(jpeg(None, seed=2))
    msg = store.add_screen("colony_prompt", shown, (576, 290, 992, 330), ScreenAction(click=(895, 525)), "desc", "ev")
    assert "active from the next turn" in msg
    m = tomllib.loads((corpus / "learned/manifest.toml").read_text())
    s = m["screens"]["colony_prompt"]
    assert s["auto_dismiss"] is True and s["template"] == "learned/templates/colony_prompt.png"
    assert s["dismiss_click"] == [0.5708, 0.5952] and s["learned_by"] == "test-model"
    assert (corpus / "learned/templates/colony_prompt.png").exists()
    ledger = [json.loads(line) for line in (corpus / "learned/ledger.jsonl").read_text().splitlines()]
    assert ledger[-1]["kind"] == "screen" and ledger[-1]["min_negative_distance"] >= 0.10


def test_learn_screen_rejects_bad_inputs(corpus):
    store = LearnedStore(corpus, "m", "r")
    store.remember_frame(jpeg(None, seed=1))
    f = jpeg("Title")
    with pytest.raises(LearningRejected, match="snake_case"):
        store.add_screen("Bad Name", f, (576, 290, 992, 330), ScreenAction(key="c"), "d", "e")
    with pytest.raises(LearningRejected, match="already exists"):
        store.add_screen("gnn_news", f, (576, 290, 992, 330), ScreenAction(key="c"), "d", "e")
    with pytest.raises(LearningRejected, match="not allowed"):
        store.add_screen("quitter", f, (576, 290, 992, 330), ScreenAction(key="alt+f4"), "d", "e")
    with pytest.raises(LearningRejected, match="tightly"):
        store.add_screen("whole_map", f, (0, 0, 1568, 882), ScreenAction(key="c"), "d", "e")
    # a box over the plain map is not distinctive against another map frame
    store.remember_frame(jpeg(None, seed=0))
    with pytest.raises(LearningRejected, match="not distinctive|no frames"):
        store.add_screen("map_patch", jpeg(None, seed=0), (100, 100, 300, 160), ScreenAction(key="c"), "d", "e")


def test_failing_learned_screen_is_disabled(corpus):
    store = LearnedStore(corpus, "m", "r")
    store.remember_frame(jpeg(None, seed=3))
    store.add_screen("pesky", jpeg("Pesky"), (576, 290, 992, 330), ScreenAction(key="c"), "d", "e")
    assert store.record_dismissals(["pesky"], advanced=False) == []
    assert store.record_dismissals(["pesky", "gnn_news"], advanced=False) == []
    assert store.record_dismissals(["pesky"], advanced=False) == ["pesky"]
    s = store.screens()["pesky"]
    assert s["auto_dismiss"] is False and "without the turn advancing" in s["disabled_reason"]


def test_rules_controls_episodes_and_recall(corpus, tmp_path):
    store = LearnedStore(corpus, "m", "r")
    with pytest.raises(LearningRejected):
        store.add_rule("short", "x")
    store.add_rule("When offered an artifact or 200 credits, take the artifact while rich.", "recurring")
    store.add_control("Key n puts a warship on Sentry.", "tooltip")
    assert "take the artifact" in (corpus / "learned/strategy.md").read_text()
    store.add_episode("Event: Space Creature Migration", "Protected the creatures", "resolved", "Jul 2333")
    store.add_episode("Event: Space Creature Migration", "Protected the creatures", "resolved", "Jul 2334")
    store.add_episode("Research complete", "Chose Hyperwave Radio", "resolved")
    assert store.recall("space creature")[0]["decision"] == "Protected the creatures"
    assert store.repeated("Event: Space Creature Migration") == 2
    j = Journal(tmp_path / "j.md", "m")
    j.note("Colonised Artemis", "Aug 2330")
    j.note("Second line")
    text = (tmp_path / "j.md").read_text()
    assert "## Pilot log" in text and "**Aug 2330**: Colonised Artemis" in text and text.count("## Pilot log") == 1


# -- history trimming ----------------------------------------------------------------------------

def test_undecodable_frame_is_ignored(corpus):
    store = LearnedStore(corpus, "m", "r")
    store.remember_frame(b"not a jpeg")
    store.remember_frame(jpeg(None))
    assert len(store.negatives) == 1


def test_trim_images_keeps_only_the_newest():
    img = BinaryContent(data=b"x", media_type="image/jpeg")
    msgs = [ModelRequest(parts=[UserPromptPart(content=["a", img])]) for _ in range(4)]
    out = trim_images(2)(msgs)
    kept = [p.content[1] for m in out for p in m.parts]
    assert kept[:2] == [IMAGE_STUB, IMAGE_STUB] and all(isinstance(k, BinaryContent) for k in kept[2:])


# -- the loop, end to end with a scripted model -------------------------------------------------

def scripted_model():
    """Episode 1: consult, click the button (norm1000), learn nothing, return a result."""

    def respond(messages, info: AgentInfo) -> ModelResponse:
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step == 0:
            return ModelResponse(parts=[ToolCallPart("consult", {"situation": "Event: Space Creature Migration"})])
        if step == 1:
            return ModelResponse(parts=[ToolCallPart("click", {"x": 306, "y": 701})])
        if step == 2:
            return ModelResponse(parts=[ToolCallPart("note", {"text": "Protected the space creatures", "game_date": "Jul 2333"})])
        out = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(out, {"situation": "Event: Space Creature Migration",
                                                       "decision": "Protect the creatures", "game_date": "Jul 1, 2333",
                                                       "resolved": True})])

    return FunctionModel(respond)


def test_pilot_loop_resolves_a_blocker_and_records_it(corpus, tmp_path):
    s = Settings(model="google:gemini-3.8-flash", runs_dir=tmp_path / "runs", journal=tmp_path / "journal.md",
                 commit_learnings=False, game="x")
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    game = FakeGame([TurnReport(2, "dialog", "Advanced 2 turn(s), then stopped at turn 3: a dialog is up", jpeg("Event")),
                     TurnReport(5, "limit", "Advanced 5 turn(s); each verified.\nDismissed on advanced turns: gnn_news.", jpeg(None))],
                    frame=jpeg(None, seed=4))
    log = EventLog(s.runs_dir, "run1", s.model)
    pilot = Pilot(s, game, log, model=scripted_model())
    pilot.run(max_episodes=1)

    assert ("click", 480, 618, "left", 1) in game.actions, game.actions   # 306,701 in 0-1000 -> image px
    kinds = [e["kind"] for e in log.recent]
    assert {"autopilot", "consult", "action", "journal", "episode", "run_end"} <= set(kinds)
    ep = next(e for e in log.recent if e["kind"] == "episode")
    assert ep["resolved"] is True and ep["situation"] == "Event: Space Creature Migration"
    assert log.state.episodes == 1 and log.state.turns_advanced == 2 and log.state.game_date == "Jul 1, 2333"
    assert "Protected the space creatures" in (tmp_path / "journal.md").read_text()
    assert LearnedStore(corpus, "m", "r").recall("space creature")
    assert (log.dir / "events.jsonl").exists() and (log.dir / "latest.jpg").exists()


def test_dashboard_status_and_control(corpus, tmp_path):
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from pilot.dashboard import make_app

    s = Settings(runs_dir=tmp_path / "runs", journal=tmp_path / "j.md", commit_learnings=False)
    s.__class__ = type("S", (Settings,), {"corpus_dir": property(lambda self: corpus)})
    log = EventLog(s.runs_dir, "run2", s.model)
    pilot = Pilot(s, FakeGame([]), log, model=scripted_model())

    async def go():
        async with TestClient(TestServer(make_app(pilot))) as c:
            st = await (await c.get("/status")).json()
            assert st["run_id"] == "run2"
            r = await c.post("/control", json={"action": "pause"})
            assert (await r.json())["status"] == "paused" and pilot.control.paused
            await c.post("/control", json={"action": "instruct", "text": "prioritise research"})
            assert pilot.human.take_all() == ["prioritise research"]
            assert (await c.post("/control", json={"action": "nope"})).status == 400
            assert (await c.get("/")).status == 200

    asyncio.run(go())


def test_stop_grace_forces_exit_when_a_step_hangs():
    import threading
    import time as _t

    from pilot.cli import arm_stop_grace
    exits, forced = [], []
    done = threading.Event()
    arm_stop_grace(done, 0.05, on_force=lambda: forced.append(1), force_exit=exits.append).join(1)
    assert exits == [0] and forced == [1], "a model call that never returns must not block the stop"

    exits.clear()
    t = arm_stop_grace(done, 0.2, force_exit=exits.append)
    _t.sleep(0.02)
    done.set()
    t.join(1)
    assert exits == [], "a run that ends within the grace period exits normally"


def test_model_calls_retry_transient_errors_and_timeouts():
    import httpx
    from pydantic_ai.exceptions import ModelHTTPError

    from pilot.agent import run_with_retry
    errors = [ModelHTTPError(503, "m"), httpx.ReadTimeout("slow"), TimeoutError()]
    seen = []

    def call():
        if errors:
            raise errors.pop(0)
        return "ok"
    assert run_with_retry(call, (0, 0, 0), on_retry=lambda e, d, i: seen.append(type(e).__name__)) == "ok"
    assert seen == ["ModelHTTPError", "ReadTimeout", "TimeoutError"]

    def always_slow():
        raise httpx.ReadTimeout("slow")
    with pytest.raises(httpx.ReadTimeout):
        run_with_retry(always_slow, (0,))

    def bad_request():
        raise ModelHTTPError(400, "m")
    with pytest.raises(ModelHTTPError):
        run_with_retry(bad_request, (0, 0))


def test_every_model_call_has_a_timeout():
    from dataclasses import replace

    from pilot.agent import model_settings
    s = Settings()
    for thinking in ("off", "medium"):
        assert model_settings(replace(s, thinking=thinking))["timeout"] == s.model_timeout_s
