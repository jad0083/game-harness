"""Learned knowledge in the store (docs/design/2026-10-05-data-platform-design.md, rulings 4 and 7).

    learned_notes    decision rules found in play (kind 'rule') and UI behaviour / hotkeys verified
                     in play (kind 'control'), in the order added
    learned_screens  known screens: description, template region and threshold, dismiss action and
                     the template image (png)
    episodes         every resolved blocker: situation, decision, outcome (retrieval memory)
    ledger           provenance of every learned item (model, run, evidence, status)
    journal          the pilot's journal lines, per campaign (Journal)

When a LearnedStore starts, and after every change to a game's screens or notes, the overlay the
controller reads is generated from the store into <data>/learned/<game>/ (learned_files.py):
manifest.toml (known screens, merged by the Rust loader, main wins), templates/*.png, strategy.md
and controls.md. Nothing is written into the corpora.

Learned items are active immediately. A learned screen that is dismissed repeatedly without the
turn advancing is disabled automatically. Promotion into the main corpus is a human/maintainer step.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .coords import IMAGE_H, IMAGE_W, to_norm
from .learned_files import manifest_toml, notes_markdown, write_learned_dir

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
# Keys the pilot must never press: any combo with the Windows key (win+r opens Run, win+x the admin
# menu, ...), and combos that close, switch or leave the game or reach the OS (Task Manager, Start).
SYSTEM_KEYS = frozenset({"win", "lwin", "rwin", "super", "meta", "windows", "cmd"})
FORBIDDEN_COMBOS = frozenset(frozenset(c.split("+")) for c in (
    "alt+f4", "ctrl+f4", "ctrl+alt+delete", "ctrl+alt+del", "ctrl+shift+esc", "ctrl+shift+escape",
    "alt+tab", "alt+shift+tab", "ctrl+alt+tab", "alt+esc", "alt+escape", "ctrl+esc", "ctrl+escape",
    "alt+space", "delete", "del"))


def is_forbidden_key(combo: str) -> bool:
    """Whether a key combo ('Win + R', 'alt+f4') is one the pilot may not press."""
    parts = frozenset(p for p in combo.lower().replace(" ", "").split("+") if p)
    return bool(parts & SYSTEM_KEYS) or parts in FORBIDDEN_COMBOS
MIN_DISTINCTNESS = 0.10      # template distance on frames without the screen must exceed this
MATCH_THRESHOLD = 0.06       # manifest template_threshold for learned screens
DISABLE_AFTER_FAILURES = 3


class LearningRejected(ValueError):
    """A proposed learning failed validation; the message tells the model why."""


def _diff(a: Image.Image, b: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3 / 255


def _stamp(micro: bool = False) -> str:
    """Local time, ISO 8601 to the second (to the microsecond with `micro`)."""
    now = time.time()
    s = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
    return f"{s}.{int(now % 1 * 1_000_000):06d}" if micro else s


@dataclass
class ScreenAction:
    click: tuple[int, int] | None = None     # image pixels
    key: str | None = None

    def stored(self) -> dict:
        """The action as learned_screens.action holds it: a click in normalized coordinates, or a key."""
        if self.click:
            return {"click": list(to_norm(*self.click))}
        return {"key": self.key or ""}


class LearnedStore:
    """One game's learned knowledge in the store (`store`, a Store), with its generated overlay in
    `learned_dir` (<data>/learned/<game>). `corpus_dir` is only read (the main manifest's screen names)."""

    def __init__(self, store, game: str, corpus_dir: Path, learned_dir: Path, model: str, run_id: str):
        self.store, self.game = store, game
        self.corpus_dir, self.learned_dir = Path(corpus_dir), Path(learned_dir)
        self.model, self.run_id = model, run_id
        self.failures: dict[str, int] = {}
        self.negatives: list[Image.Image] = []   # recent frames, used to test distinctness
        self._write_files()                      # the controller always reads the current overlay

    def _write_files(self) -> None:
        """Regenerate the learned directory from the store (after every change to screens or notes)."""
        write_learned_dir(self.store, self.game, self.learned_dir)

    # -- provenance -------------------------------------------------------------------------

    def _ledger(self, kind: str, name: str, **data) -> None:
        rec = {"name": name, "model": self.model, "run": self.run_id, **data}
        self.store._exec("INSERT INTO ledger(game, t, kind, data) VALUES (?,?,?,?)",
                         (self.game, _stamp(), kind, json.dumps(rec, ensure_ascii=False)))

    def remember_frame(self, jpeg: bytes | None) -> None:
        """Keep a few recent frames as negatives for template validation."""
        if not jpeg:
            return
        try:
            img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        except (OSError, ValueError):
            return  # an undecodable frame is simply not used as a negative
        if img.size == (IMAGE_W, IMAGE_H):
            self.negatives = (self.negatives + [img])[-12:]

    # -- screens ----------------------------------------------------------------------------

    def screens(self) -> dict:
        """The learned screens as the controller reads them: the generated manifest's [screens.*] tables."""
        return tomllib.loads(manifest_toml(self.store, self.game)).get("screens", {})

    def main_screen_names(self) -> set[str]:
        for f in ("manifest.toml", "game.toml"):
            p = self.corpus_dir / f
            if p.exists():
                return set(tomllib.loads(p.read_text(encoding="utf-8")).get("screens", {}))
        return set()

    def add_screen(self, name: str, frame_jpeg: bytes, box: tuple[int, int, int, int], action: ScreenAction,
                   description: str, evidence: str) -> str:
        """Validate and store a learned known screen. `box` and `action.click` are image pixels."""
        if not NAME_RE.match(name):
            raise LearningRejected("name must be snake_case, 3-41 chars, starting with a letter")
        if name in self.main_screen_names() or name in self.screens():
            raise LearningRejected(f"a screen named {name!r} already exists; pick another name")
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= IMAGE_W and 0 <= y0 < y1 <= IMAGE_H):
            raise LearningRejected("box must be inside the frame with x0 < x1 and y0 < y1")
        if (x1 - x0) * (y1 - y0) < 300 or (x1 - x0) > 700 or (y1 - y0) > 400:
            raise LearningRejected("box should tightly cover a static label/title/icon (>= 300 px area, <= 700x400)")
        if action.key and is_forbidden_key(action.key):
            raise LearningRejected(f"key {action.key!r} is not allowed for automatic actions")
        if not action.click and not action.key:
            raise LearningRejected("an action (click point or key) is required")
        frame = Image.open(io.BytesIO(frame_jpeg)).convert("RGB")
        tpl = frame.crop(box)
        # Distinctness: the same region of recent frames that do NOT show this screen must differ.
        dists = [_diff(n.crop(box), tpl) for n in self.negatives]
        dists = [d for d in dists if d > 0.02]       # frames that do show the screen are not negatives
        if not dists:
            raise LearningRejected("no frames without this screen to compare against yet; resolve it by hand this time")
        worst = min(dists)
        if worst < MIN_DISTINCTNESS:
            raise LearningRejected(f"template is not distinctive enough (distance {worst:.3f} on another frame, "
                                   f"need >= {MIN_DISTINCTNESS}); choose a box around a unique title or icon")
        png = io.BytesIO()
        tpl.save(png, "PNG")
        nx, ny = to_norm(x0, y0)
        nw, nh = round((x1 - x0) / IMAGE_W, 4), round((y1 - y0) / IMAGE_H, 4)
        try:
            self.store._exec(
                "INSERT INTO learned_screens(game, name, description, roi, threshold, auto_dismiss, action, png,"
                " learned_by, run_id, t, disabled_reason) VALUES (?,?,?,?,?,1,?,?,?,?,?,NULL)",
                (self.game, name, description, f"[{nx}, {ny}, {nw}, {nh}]", MATCH_THRESHOLD,
                 json.dumps(action.stored()), png.getvalue(), self.model, self.run_id, _stamp()))
        except sqlite3.IntegrityError:      # stored meanwhile (another thread or run of the same game)
            raise LearningRejected(f"a screen named {name!r} already exists; pick another name") from None
        self._write_files()
        self._ledger("screen", name, description=description, evidence=evidence,
                     min_negative_distance=round(worst, 3), negatives=len(dists))
        return f"learned screen {name!r} (min distance on other frames {worst:.3f}); active from the next turn"

    def record_dismissals(self, dismissed: list[str], advanced: bool) -> list[str]:
        """Track learned screens that were dismissed; disable ones that keep failing. Returns disabled names."""
        learned = self.screens()
        disabled = []
        for name in dismissed:
            if name not in learned:
                continue
            if advanced:
                self.failures[name] = 0
                continue
            self.failures[name] = self.failures.get(name, 0) + 1
            if self.failures[name] >= DISABLE_AFTER_FAILURES:
                self._disable(name, f"dismissed {DISABLE_AFTER_FAILURES} times without the turn advancing")
                disabled.append(name)
        return disabled

    def _disable(self, name: str, reason: str) -> None:
        self.store._exec("UPDATE learned_screens SET auto_dismiss=0, disabled_reason=? WHERE game=? AND name=?",
                         (reason, self.game, name))
        self._write_files()
        self._ledger("screen_disabled", name, reason=reason)

    # -- notes ------------------------------------------------------------------------------

    def _add_note(self, kind: str, text: str, why: str) -> None:
        """A rule or control, once per text (the same text again is kept as first written)."""
        self.store._exec("INSERT OR IGNORE INTO learned_notes(game, kind, text, why, model, run_id, t)"
                         " VALUES (?,?,?,?,?,?,?)",
                         (self.game, kind, text.strip(), why.strip(), self.model, self.run_id, _stamp()))
        self._write_files()

    # known-false rules of this game (pillars.toml [learned] refuse: (regex, why); set by the governor)
    refuse: tuple[tuple[str, str], ...] = ()

    def add_rule(self, rule: str, why: str) -> str:
        if len(rule) < 15:
            raise LearningRejected("state the rule as a full sentence (situation -> choice)")
        for pattern, reason in self.refuse:          # postmortem-fixes design, ruling 29
            # the why is written beside the rule, so a false premise there is refused too
            if re.search(pattern, f"{rule}\n{why}", re.IGNORECASE):
                raise LearningRejected(f"refused: {reason}")
        self._add_note("rule", rule, why)
        self._ledger("rule", rule[:60], why=why)
        return "rule recorded"

    def add_control(self, control: str, how_verified: str) -> str:
        self._add_note("control", control, how_verified)
        self._ledger("control", control[:60], verified=how_verified)
        return "control recorded"

    def rules_markdown(self) -> str:
        """The learned rules as strategy.md holds them; '' while the game has none."""
        if not self.store.query("SELECT 1 FROM learned_notes WHERE game=? AND kind='rule' LIMIT 1", (self.game,)):
            return ""
        return notes_markdown(self.store, self.game, "rule")

    # -- episode memory ---------------------------------------------------------------------

    def add_episode(self, situation: str, decision: str, outcome: str, game_date: str = "") -> None:
        # microseconds: the same situation resolved twice within a second is two episodes (t is in their key)
        self.store._exec("INSERT OR IGNORE INTO episodes(game, t, date, situation, decision, outcome, model, run_id)"
                         " VALUES (?,?,?,?,?,?,?,?)",
                         (self.game, _stamp(micro=True), game_date, situation, decision, outcome, self.model,
                          self.run_id))

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
        scored = []
        for e in self.store.query("SELECT situation, decision, outcome, date, model, run_id AS run, t FROM episodes"
                                  " WHERE game=? ORDER BY rowid", (self.game,)):
            hay = f"{e['situation'] or ''} {e['decision'] or ''}".lower()
            score = sum(w in hay for w in words)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda p: -p[0])
        return [e for _, e in scored[:limit]]

    def repeated(self, situation: str) -> int:
        """How many past episodes had this exact situation."""
        return sum(1 for e in self.recall(situation, limit=100) if (e["situation"] or "").lower() == situation.lower())


class Journal:
    """The pilot's journal: one row per line in the store's journal table, under the run's campaign
    (`campaign()`, '<game>/no-campaign' until the run has named it), dated by in-game date when known."""

    def __init__(self, store, game: str, model: str, campaign: Callable[[], str | None]):
        self.store, self.game, self.model, self.campaign = store, game, model, campaign

    def note(self, text: str, game_date: str = "") -> None:
        self.store._exec("INSERT OR IGNORE INTO journal(campaign_id, game, t, date, text) VALUES (?,?,?,?,?)",
                         (self.campaign() or f"{self.game}/no-campaign", self.game, time.time(), game_date,
                          text.strip()))
