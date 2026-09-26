"""The pilot loop: autopilot for routine turns, an LLM episode for each blocker, learning and
journal updates, CI-gated commits of what was learned, and pause/resume/stop control."""

from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import dataclass

from .agent import Deps, HumanChannel, build_agent, run_episode
from .config import REPO, Settings
from .events import EventLog
from .game import Game
from .learning import Journal, LearnedStore

DISMISSED_RE = re.compile(r"Dismissed on advanced turns: (.+)\.")
ALREADY_RE = re.compile(r"already dismissed: ([^)]+)\)")
MAX_UNRESOLVED = 3          # consecutive unresolved episodes before pausing for a human
MAX_PROCESSING = 3          # consecutive "still processing" stops (each up to 180 s) before alerting


@dataclass
class Control:
    paused: bool = False
    stopping: bool = False


class Pilot:
    def __init__(self, settings: Settings, game: Game, log: EventLog, model=None):
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
        self.agent = build_agent(settings, briefing, model=model)
        self._learned_since_commit = 0
        self._commit_lock = threading.Lock()

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

    def _status(self, status: str) -> None:
        self.log.state.status = status
        self.log.emit("status", status=status)

    # -- main loop --------------------------------------------------------------------------------

    def run(self, max_episodes: int | None = None) -> None:
        self._status("playing")
        self.log.emit("run_start", model=self.s.model, coords=self.s.coord_space)
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
                                              "(possible GC4 turn hang; see AGENTS.md §7)")
                    continue
                if report.stop == "error":
                    self._needs_attention(f"autopilot error: {report.text[:200]}")
                    continue
                processing = 0

                resolved = self._episode(report.text, report.frame)
                unresolved = 0 if resolved else unresolved + 1
                if unresolved >= MAX_UNRESOLVED:
                    self._needs_attention(f"{MAX_UNRESOLVED} blockers in a row were not resolved")
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
            result, usage = run_episode(self.agent, deps, stop_text, frame, extra)
        except Exception as e:  # noqa: BLE001 - a failed episode must not end the run
            self.log.emit("episode_error", error=f"{type(e).__name__}: {e}"[:500])
            self._status("playing")
            return False
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

    def _needs_attention(self, why: str) -> None:
        self.log.emit("needs_attention", reason=why)
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
                body = f"Learned during play by {self.s.model}, run {self.log.state.run_id}."
                r = subprocess.run(["scripts/ci-commit.sh", message, body], cwd=REPO, capture_output=True, text=True, check=False)
                self.log.emit("commit", ok=r.returncode == 0, output=(r.stdout + r.stderr)[-400:])

        t = threading.Thread(target=work, daemon=not force)
        t.start()
        if force:
            t.join(timeout=900)
