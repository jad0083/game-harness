"""The corpus overlay the pilot learns into: corpora/<game>/learned/.

    learned/manifest.toml   known screens (and hotkeys) - merged by the Rust loader, main wins
    learned/templates/*.png templates for those screens
    learned/strategy.md     decision rules found in play
    learned/controls.md     UI behaviour / hotkeys verified in play
    learned/episodes.jsonl  every resolved blocker: situation, decision, outcome (retrieval memory)
    learned/ledger.jsonl    provenance of every learned item (model, run, evidence, status)

Learned items are active immediately. A learned screen that is dismissed repeatedly without the
turn advancing is disabled automatically. Promotion into the main corpus is a human/maintainer step.
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from .coords import IMAGE_H, IMAGE_W, to_norm

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
FORBIDDEN_KEYS = {"alt+f4", "ctrl+alt+delete", "ctrl+alt+del", "delete", "del", "win", "lwin", "rwin"}
MIN_DISTINCTNESS = 0.10      # template distance on frames without the screen must exceed this
MATCH_THRESHOLD = 0.06       # manifest template_threshold for learned screens
DISABLE_AFTER_FAILURES = 3


class LearningRejected(ValueError):
    """A proposed learning failed validation; the message tells the model why."""


def _diff(a: Image.Image, b: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3 / 255


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # JSON string syntax is valid TOML basic string


@dataclass
class ScreenAction:
    click: tuple[int, int] | None = None     # image pixels
    key: str | None = None

    def toml(self) -> str:
        if self.click:
            nx, ny = to_norm(*self.click)
            return f"dismiss_click = [{nx}, {ny}]"
        return f"dismiss_key = {_toml_str(self.key or '')}"


class LearnedStore:
    def __init__(self, corpus_dir: Path, model: str, run_id: str):
        self.dir = corpus_dir / "learned"
        (self.dir / "templates").mkdir(parents=True, exist_ok=True)
        self.corpus_dir = corpus_dir
        self.model, self.run_id = model, run_id
        self._lock = threading.Lock()
        self.failures: dict[str, int] = {}
        self.negatives: list[Image.Image] = []   # recent frames, used to test distinctness

    # -- provenance -------------------------------------------------------------------------

    def _ledger(self, kind: str, name: str, **data) -> None:
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "name": name,
               "model": self.model, "run": self.run_id, **data}
        with open(self.dir / "ledger.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

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
        path = self.dir / "manifest.toml"
        if not path.exists():
            return {}
        return tomllib.loads(path.read_text(encoding="utf-8")).get("screens", {})

    def main_screen_names(self) -> set[str]:
        for f in ("manifest.toml", "game.toml"):
            p = self.corpus_dir / f
            if p.exists():
                return set(tomllib.loads(p.read_text(encoding="utf-8")).get("screens", {}))
        return set()

    def add_screen(self, name: str, frame_jpeg: bytes, box: tuple[int, int, int, int], action: ScreenAction,
                   description: str, evidence: str) -> str:
        """Validate and write a learned known screen. `box` and `action.click` are image pixels."""
        if not NAME_RE.match(name):
            raise LearningRejected("name must be snake_case, 3-41 chars, starting with a letter")
        if name in self.main_screen_names() or name in self.screens():
            raise LearningRejected(f"a screen named {name!r} already exists; pick another name")
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= IMAGE_W and 0 <= y0 < y1 <= IMAGE_H):
            raise LearningRejected("box must be inside the frame with x0 < x1 and y0 < y1")
        if (x1 - x0) * (y1 - y0) < 300 or (x1 - x0) > 700 or (y1 - y0) > 400:
            raise LearningRejected("box should tightly cover a static label/title/icon (>= 300 px area, <= 700x400)")
        if action.key and action.key.lower().replace(" ", "") in FORBIDDEN_KEYS:
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
        rel = f"learned/templates/{name}.png"
        with self._lock:
            tpl.save(self.corpus_dir / rel)
            nx, ny = to_norm(x0, y0)
            nw, nh = round((x1 - x0) / IMAGE_W, 4), round((y1 - y0) / IMAGE_H, 4)
            block = (f"\n[screens.{name}]\n"
                     f"description = {_toml_str(description)}\n"
                     f"template = {_toml_str(rel)}\n"
                     f"template_roi = [{nx}, {ny}, {nw}, {nh}]\n"
                     f"template_threshold = {MATCH_THRESHOLD}\n"
                     f"auto_dismiss = true\n{action.toml()}\n"
                     f"learned_by = {_toml_str(self.model)}\n"
                     f"learned_run = {_toml_str(self.run_id)}\n")
            path = self.dir / "manifest.toml"
            if not path.exists():
                path.write_text("# Known screens learned during play (pilot app). Main manifest wins on name clashes.\n")
            with open(path, "a", encoding="utf-8") as f:
                f.write(block)
            tomllib.loads(path.read_text(encoding="utf-8"))  # never leave an unparsable overlay
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
        path = self.dir / "manifest.toml"
        with self._lock:
            text = path.read_text(encoding="utf-8")
            head = f"[screens.{name}]\n"
            i = text.index(head)
            j = text.find("\n[", i + len(head))
            block = text[i: j if j != -1 else len(text)]
            new = block.replace("auto_dismiss = true", f"auto_dismiss = false\ndisabled_reason = {_toml_str(reason)}")
            path.write_text(text.replace(block, new))
            tomllib.loads(path.read_text(encoding="utf-8"))
        self._ledger("screen_disabled", name, reason=reason)

    # -- notes ------------------------------------------------------------------------------

    def _append_note(self, file: str, title: str, text: str, why: str) -> None:
        path = self.dir / file
        with self._lock:
            if not path.exists():
                path.write_text(f"# {title}\n\nWritten by the pilot app during play; promote proven items into the main corpus.\n")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n- {text.strip()}  \n  _why:_ {why.strip()} _({self.model}, {time.strftime('%Y-%m-%d')})_\n")

    def add_rule(self, rule: str, why: str) -> str:
        if len(rule) < 15:
            raise LearningRejected("state the rule as a full sentence (situation -> choice)")
        self._append_note("strategy.md", "Learned strategy rules", rule, why)
        self._ledger("rule", rule[:60], why=why)
        return "rule recorded in learned/strategy.md"

    def add_control(self, control: str, how_verified: str) -> str:
        self._append_note("controls.md", "Learned controls (verified in play)", control, how_verified)
        self._ledger("control", control[:60], verified=how_verified)
        return "control recorded in learned/controls.md"

    # -- episode memory ---------------------------------------------------------------------

    def add_episode(self, situation: str, decision: str, outcome: str, game_date: str = "") -> None:
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "date": game_date, "situation": situation,
               "decision": decision, "outcome": outcome, "model": self.model, "run": self.run_id}
        with open(self.dir / "episodes.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        path = self.dir / "episodes.jsonl"
        if not path.exists():
            return []
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
        scored = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            hay = f"{e.get('situation', '')} {e.get('decision', '')}".lower()
            score = sum(w in hay for w in words)
            if score:
                scored.append((score, e))
        scored.sort(key=lambda p: -p[0])
        return [e for _, e in scored[:limit]]

    def repeated(self, situation: str) -> int:
        """How many past episodes had this exact situation."""
        return sum(1 for e in self.recall(situation, limit=100) if e.get("situation", "").lower() == situation.lower())


class Journal:
    """Appends to the game journal under a pilot section, dated by in-game month when known."""

    def __init__(self, path: Path, model: str):
        self.path, self.model = path, model

    def note(self, text: str, game_date: str = "") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.path.read_text(encoding="utf-8") if self.path.exists() else "# Journal\n"
        header = "\n## Pilot log\n"
        if header.strip() not in existing:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(header + f"Entries written by the pilot app ({self.model}).\n")
        stamp = f"**{game_date}**: " if game_date else ""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"- {stamp}{text.strip()}\n")
