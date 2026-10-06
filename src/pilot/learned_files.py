"""The learned files generated from the store (data platform design, ruling 7): the overlay manifest,
its templates and the notes, in the formats the Rust controller and the old learned/ folder used."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

NOTE_FILES = {"rule": ("strategy.md", "Learned strategy rules"),
              "control": ("controls.md", "Learned controls (verified in play)")}
_WRITE_LOCK = threading.Lock()      # one swap of a learned directory at a time in this process


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # JSON string syntax is valid TOML basic string


def notes_markdown(store, game: str, kind: str) -> str:
    """One kind of note ('rule' or 'control') as the markdown file it had: a title, then one item per note."""
    title = NOTE_FILES[kind][1]
    out = [f"# {title}\n\nWritten by the pilot app during play; promote proven items into the main corpus.\n"]
    for r in store.query("SELECT text, why, model, t FROM learned_notes WHERE game=? AND kind=? ORDER BY rowid",
                         (game, kind)):
        out.append(f"\n- {r['text'].strip()}  \n  _why:_ {r['why'].strip()} _({r['model']}, {(r['t'] or '')[:10]})_\n")
    return "".join(out)


def manifest_toml(store, game: str) -> str:
    """The learned screens as the overlay manifest; template paths are relative to the learned directory."""
    out = ["# Known screens learned during play (pilot app). Main manifest wins on name clashes.\n"]
    for r in store.query("SELECT * FROM learned_screens WHERE game=? ORDER BY rowid", (game,)):
        action = json.loads(r["action"] or "{}")
        lines = [f"\n[screens.{r['name']}]", f"description = {_toml_str(r['description'] or '')}",
                 f"template = {_toml_str('templates/' + r['name'] + '.png')}",
                 f"template_roi = {r['roi']}", f"template_threshold = {r['threshold']}",
                 f"auto_dismiss = {'true' if r['auto_dismiss'] else 'false'}"]
        if r["disabled_reason"]:
            lines.append(f"disabled_reason = {_toml_str(r['disabled_reason'])}")
        if action.get("click"):
            lines.append(f"dismiss_click = [{action['click'][0]}, {action['click'][1]}]")
        else:
            lines.append(f"dismiss_key = {_toml_str(action.get('key') or '')}")
        lines += [f"learned_by = {_toml_str(r['learned_by'] or '')}", f"learned_run = {_toml_str(r['run_id'] or '')}"]
        out.append("\n".join(lines) + "\n")
    return "".join(out)


def render(store, game: str) -> dict[str, bytes]:
    """Every generated file of one game, by path relative to its learned directory."""
    files = {"manifest.toml": manifest_toml(store, game).encode(),
             "strategy.md": notes_markdown(store, game, "rule").encode(),
             "controls.md": notes_markdown(store, game, "control").encode()}
    for r in store.query("SELECT name, png FROM learned_screens WHERE game=? AND png IS NOT NULL", (game,)):
        files[f"templates/{r['name']}.png"] = bytes(r["png"])
    return files


def write_learned_dir(store, game: str, out_dir: Path) -> None:
    """Write the generated files into `out_dir`, replacing it whole: a reader never sees a half-written one.
    Each write renders the store as it is then, so the last of several writers leaves the latest state."""
    out_dir = Path(out_dir)
    with _WRITE_LOCK:
        out_dir.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}-", dir=out_dir.parent))
        try:
            for rel, data in render(store, game).items():
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                (tmp / rel).write_bytes(data)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)       # no half-written temporary directory is left behind
            raise
        old = out_dir.with_name(f".{out_dir.name}-old")
        if out_dir.exists():
            if old.exists():
                shutil.rmtree(old)
            os.rename(out_dir, old)
        os.rename(tmp, out_dir)
        if old.exists():
            shutil.rmtree(old, ignore_errors=True)
