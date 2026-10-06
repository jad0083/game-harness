"""The pilot loop: autopilot for routine turns, an LLM episode for each blocker, learning and
journal updates, CI-gated commits of what was learned, and pause/resume/stop control."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import dataclass, replace

from pydantic_ai import ModelSettings

from .agent import Deps, HumanChannel, build_agent, model_settings, run_episode
from .config import REPO, Settings
from .events import EventLog
from .game import Game
from .learning import Journal, LearnedStore
from .modelguard import GuardConfig, GuardedModel, ModelHealth, PoolModel, emit_breaker
from .trace import serialize
from .wording import attention

DISMISSED_RE = re.compile(r"Dismissed on advanced turns: (.+)\.")
ALREADY_RE = re.compile(r"already dismissed: ([^)]+)\)")
MAX_UNRESOLVED = 3          # consecutive unresolved episodes before pausing for a human
MAX_PROCESSING = 3          # consecutive "still processing" stops (each up to 180 s) before alerting


@dataclass
class Control:
    paused: bool = False
    stopping: bool = False


class Pilot:
    def __init__(self, settings: Settings, game: Game, log: EventLog, model=None, fallback=None):
        self.s = settings
        self.game = game
        self.log = log
        self.control = Control()
        self.human = HumanChannel()
        self.store = LearnedStore(settings.corpus_dir, settings.model, log.state.run_id)
        self.journal = Journal(settings.journal, settings.model)
        briefing = (settings.corpus_dir / "pilot.md").read_text(encoding="utf-8")
        learned_rules = settings.corpus_dir / "learned" / "strategy.md"
        if learned_rules.exists():
            briefing += "\n\n## Rules learned in play\n" + learned_rules.read_text(encoding="utf-8")
        self._briefing = briefing
        # the model guard (docs/design/2026-10-02-model-guard-design.md): with PILOT_MODEL_GUARD=0 its usage
        # file is neither read nor written and no model health is published
        guard = GuardConfig.from_settings(settings)
        self.health = ModelHealth(guard if settings.model_guard else replace(guard, usage_file=None),
                                  on_change=self._on_breaker,
                                  on_note=lambda text: log.emit("briefing_error", error=f"model guard: {text}"[:300]))
        self._model_obj, self._fallback_obj = model, fallback
        self.pool: PoolModel | None = None
        self.agent = self._make_agent()
        self._learned_since_commit = 0
        self._commit_lock = threading.Lock()

    def _on_breaker(self, model: str, snap: dict) -> None:
        emit_breaker(self.log.emit, model, snap)
        self._publish_health()

    def _publish_health(self) -> None:
        """Now's model-health line and the pool editor's counts read this (ruling 23): after every breaker
        change and every episode's model run; nothing with PILOT_MODEL_GUARD=0."""
        if self.s.model_guard:
            self.log.state.info["model_health"] = self.health.snapshot()

    def _make_agent(self):
        """The episode agent: with the model guard, on a pool of the model and the fallback model (ruling 18)."""
        if not self.s.model_guard:
            return build_agent(self.s, self._briefing, model=self._model_obj)
        entries = [(self._model_obj or self.s.model, self.s.model)]
        if self._fallback_obj is not None:
            entries.append((self._fallback_obj, getattr(self._fallback_obj, "model_name", "fallback")))
        elif self.s.fallback_model and self.s.fallback_model != self.s.model:
            entries.append((self.s.fallback_model, self.s.fallback_model))
        self.pool = PoolModel("episodes", [GuardedModel(obj, name, self.health,
                                                        settings=model_settings(replace(self.s, model=name)))
                                           for obj, name in entries], self.health)
        return build_agent(self.s, self._briefing, model=self.pool,
                           agent_settings=ModelSettings(timeout=self.s.model_timeout_s))

    # -- control (called from the dashboard thread) ----------------------------------------------

    def pause(self) -> None:
        self.control.paused = True
        self._status("paused")

    def resume(self) -> None:
        self.control.paused = False
        self._status("playing")

    def stop(self) -> None:
        self.control.stopping = True
        self.control.paused = False

    def instruct(self, text: str) -> None:
        self.human.push(text)
        self.log.emit("instruction", text=text)

    def set_model(self, model: str, thinking: str | None = None) -> None:
        """Switch model (and thinking level) from the next episode on."""
        from .models import THINKING, valid_model
        if not valid_model(model):
            raise ValueError(f"not a model name: {model!r} (expected provider:name)")
        if thinking is not None and thinking not in THINKING:
            raise ValueError(f"thinking must be one of {', '.join(THINKING)}")
        self.s = replace(self.s, model=model, thinking=thinking or self.s.thinking)
        self._model_obj = None
        self.agent = self._make_agent()
        if self.s.model_guard and self.pool is not None:     # plan ruling P2: the new pool's models may be tried again
            self.health.clear_broken(gm.name for gm in self.pool.guarded)
            self._publish_health()
        self.log.state.model = model
        self.log.state.info["thinking"] = self.s.thinking
        self.log.emit("model", model=model, thinking=self.s.thinking)

    def answer(self, text: str) -> None:
        """Answer the model's open question (ask_human)."""
        self.human.answer(text)

    def _status(self, status: str) -> None:
        if status != "needs_attention":
            card = self.log.state.info.pop("attention", None)    # the dashboard's card goes with the stop
            if isinstance(card, dict) and card.get("frame"):
                self.log.release(card["frame"])                  # a frame captured for it (kept) may go
        if status == "deciding":                             # the dashboard's Deciding timer counts from here
            self.log.state.info["deciding"] = {"since": round(time.time(), 1)}
        else:
            self.log.state.info.pop("deciding", None)
        self.log.state.status = status
        self.log.emit("status", status=status)

    # -- main loop --------------------------------------------------------------------------------

    def run(self, max_episodes: int | None = None) -> None:
        self._status("playing")
        self.log.state.info.update(game=self.s.game, controls=["instruct", "set_model"], thinking=self.s.thinking)
        self.log.emit("run_start", model=self.s.model, game=self.s.game, coords=self.s.coord_space)
        self.log.set_campaign(self.s.game, self.s.campaign or self.s.journal.parent.name)
        unresolved = processing = 0
        try:
            while not self.control.stopping:
                if self.control.paused:
                    time.sleep(0.5)
                    continue
                report = self.game.run_turns(self.s.turns_per_autopilot)
                self.log.state.turns_advanced += report.advanced
                self.log.frame(report.frame)
                self.store.remember_frame(report.frame)
                self._judge_learned_screens(report.text, report.stop)
                self.log.state.last_stop = report.text.splitlines()[0][:200]
                self.log.emit("autopilot", advanced=report.advanced, stop=report.stop, text=report.text[:500])

                if report.stop == "limit":
                    unresolved = processing = 0
                    continue
                if report.stop == "processing":
                    processing += 1
                    if processing >= MAX_PROCESSING:
                        self._needs_attention("the game has been processing a turn for several minutes "
                                              "(possible GC4 turn hang; see AGENTS.md §7)", category="screen")
                    continue
                if report.stop == "error":
                    self._needs_attention(f"autopilot error: {report.text[:200]}", category="control_failed")
                    continue
                processing = 0

                resolved = self._episode(report.text, report.frame)
                unresolved = 0 if resolved else unresolved + 1
                if unresolved >= MAX_UNRESOLVED:
                    self._needs_attention(f"{MAX_UNRESOLVED} blockers in a row were not resolved", category="screen")
                    unresolved = 0
                if max_episodes is not None and self.log.state.episodes >= max_episodes:
                    break
        finally:
            self._commit("chore(learned): end of pilot run", force=True)
            self._status("stopped")
            self.log.emit("run_end", turns=self.log.state.turns_advanced, episodes=self.log.state.episodes)

    def _episode(self, stop_text: str, frame: bytes | None) -> bool:
        self._status("deciding")
        self.log.state.episodes += 1
        deps = Deps(self.game, self.store, self.journal, self.log, self.s, self.human)
        extra = self.human.take_all()
        started = time.time()
        try:
            result, usage, messages = run_episode(self.agent, deps, stop_text, frame, extra)
        except Exception as e:  # noqa: BLE001 - a failed episode must not end the run
            self.log.emit("episode_error", error=f"{type(e).__name__}: {e}"[:500])
            self._status("playing")
            return False
        finally:
            self._publish_health()          # today's counts, answered or not
        st = self.log.state
        st.tokens_in += getattr(usage, "input_tokens", 0) or 0
        st.tokens_out += getattr(usage, "output_tokens", 0) or 0
        st.requests += getattr(usage, "requests", 0) or 0
        st.last_decision = f"{result.situation}: {result.decision}"
        if result.game_date:
            st.game_date = result.game_date
        self.log.emit("episode", situation=result.situation, decision=result.decision, date=result.game_date,
                      resolved=result.resolved, actions=deps.actions, seconds=round(time.time() - started, 1),
                      tokens_in=getattr(usage, "input_tokens", 0), tokens_out=getattr(usage, "output_tokens", 0))
        self.store.add_episode(result.situation, result.decision, "resolved" if result.resolved else "unresolved",
                               result.game_date)
        self.log.save_trace(st.episodes, {
            "episode": st.episodes, "model": self.s.model, "game": self.s.game, "date": result.game_date,
            "trigger": stop_text[:500], "decision": result.decision, "situation": result.situation,
            "outcome": "resolved" if result.resolved else "unresolved", "seconds": round(time.time() - started, 1),
            "tokens_in": getattr(usage, "input_tokens", 0), "tokens_out": getattr(usage, "output_tokens", 0),
            "steps": serialize(messages)})
        self.journal.note(f"{result.situation} → {result.decision}", result.game_date)
        learned_now = sum(1 for e in list(self.log.recent)[-40:] if e["kind"] == "learned" and e["t"] >= started)
        if learned_now:
            self._learned_since_commit += learned_now
            self.game.reload()          # newly learned screens take effect on the next turn
            self._commit(f"feat(learned): {result.situation[:60]}")
        self._status("playing")
        return result.resolved

    def _judge_learned_screens(self, text: str, stop: str) -> None:
        ok = DISMISSED_RE.search(text)
        if ok:
            self.store.record_dismissals([n.strip() for n in ok.group(1).split(",")], advanced=True)
        bad = ALREADY_RE.search(text)
        if bad and stop in ("blocked", "dialog"):
            disabled = self.store.record_dismissals([n.strip() for n in bad.group(1).split(",")], advanced=False)
            for name in disabled:
                self.log.emit("learned_disabled", screen=name)
                self.game.reload()

    def _needs_attention(self, why: str, category: str = "screen") -> None:
        """Wait for the human; `category` (view.CATEGORIES) picks the dashboard's recovery steps."""
        self.log.state.info["attention"] = attention(why, category, list(self.log.recent), date=self.log.state.game_date,
                                                     frame=self.log.state.frame_path)
        self.log.emit("needs_attention", reason=why, category=category)
        self.log.state.status = "needs_attention"
        self.control.paused = True

    def _commit(self, message: str, force: bool = False) -> None:
        """Commit learned overlay + journal through the CI gate, in the background."""
        if not self.s.commit_learnings or (self._learned_since_commit == 0 and not force):
            return
        self._learned_since_commit = 0
        paths = [str(self.s.corpus_dir.relative_to(REPO) / "learned"), str(self.s.journal.relative_to(REPO))]

        def work() -> None:
            with self._commit_lock:
                subprocess.run(["git", "add", "--", *paths], cwd=REPO, check=False, capture_output=True)
                if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO, check=False).returncode == 0:
                    return
                body = f"Learned during pilot run {self.log.state.run_id}."
                r = subprocess.run(["scripts/ci-commit.sh", message, body], cwd=REPO, capture_output=True, text=True, check=False)
                self.log.emit("commit", ok=r.returncode == 0, output=(r.stdout + r.stderr)[-400:])

        t = threading.Thread(target=work, daemon=not force)
        t.start()
        if force:
            t.join(timeout=900)
