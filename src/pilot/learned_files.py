"""The learned files generated from the store (data platform design, ruling 7): the overlay manifest,
its templates and the notes, in the formats the Rust controller and the old learned/ folder used."""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
import threading
import tomllib
from pathlib import Path

NOTE_FILES = {"rule": ("strategy.md", "Learned strategy rules"),
              "control": ("controls.md", "Learned controls (verified in play)")}
PRODUCED = ("manifest.toml", "strategy.md", "controls.md")   # top-level names a render can produce
_WRITE_LOCK = threading.Lock()      # one write of a learned directory at a time in this process


def _toml_str(s: str) -> str:
    # JSON escapes U+0000-U+001F as TOML does; U+007F is the one other control character TOML rejects
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")


def notes_markdown(store, game: str, kind: str) -> str:
    """One kind of note ('rule' or 'control') as the markdown file it had: a title, then one item per note.
    A note with no model (a rule corrected by hand, imported without the `_(model, date)_` suffix) is
    written without that suffix, as its file had it."""
    title = NOTE_FILES[kind][1]
    out = [f"# {title}\n\nWritten by the pilot app during play; promote proven items into the main corpus.\n"]
    for r in store.query("SELECT text, why, model, t FROM learned_notes WHERE game=? AND kind=? ORDER BY rowid",
                         (game, kind)):
        by = f" _({r['model']}, {(r['t'] or '')[:10]})_" if r["model"] is not None else ""
        out.append(f"\n- {r['text'].strip()}  \n  _why:_ {r['why'].strip()}{by}\n")
    return "".join(out)


def _screen_block(r: dict) -> str:
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
    return "\n".join(lines) + "\n"


def manifest_toml(store, game: str) -> str:
    """The learned screens as the overlay manifest; template paths are relative to the learned directory.
    A row that cannot be rendered as valid TOML (a NULL region or threshold, a damaged action) is left out
    and named in one comment line, so one bad row never costs the controller the others."""
    out, skipped = ["# Known screens learned during play (pilot app). Main manifest wins on name clashes.\n"], []
    for r in store.query("SELECT * FROM learned_screens WHERE game=? ORDER BY rowid", (game,)):
        try:
            block = _screen_block(r)
            tomllib.loads(block)
        except (ValueError, TypeError, KeyError, IndexError):     # TOMLDecodeError, bad JSON action, ...
            skipped.append(str(r["name"]))
            continue
        out.append(block)
    if skipped:
        out.insert(1, "# skipped (cannot be rendered): " + ", ".join(n.replace("\n", " ") for n in skipped) + "\n")
    return "".join(out)


def render(store, game: str) -> dict[str, bytes]:
    """Every generated file of one game, by path relative to its learned directory."""
    files = {"manifest.toml": manifest_toml(store, game).encode(),
             "strategy.md": notes_markdown(store, game, "rule").encode(),
             "controls.md": notes_markdown(store, game, "control").encode()}
    for r in store.query("SELECT name, png FROM learned_screens WHERE game=? AND png IS NOT NULL", (game,)):
        files[f"templates/{r['name']}.png"] = bytes(r["png"])
    return files


def _put(path: Path, data: bytes) -> None:
    """Replace `path` with `data` in one step: a reader sees the old file or the new one, never half."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_learned_dir(store, game: str, out_dir: Path) -> None:
    """Write the generated files into `out_dir` in place, so that every state a running controller can
    read is consistent (ruling 7): templates first, `manifest.toml` last (it names the templates), then
    files the render no longer produces are removed. The directory itself is never removed or renamed.
    A manifest that is not valid TOML as a whole is never written: the previous files stay and one line
    on stderr names the game (a single bad screen row is already left out of the manifest). Writers are serialised across processes by an exclusive lock on `<data>/learned/.lock`.
    Each write renders the store as it is then, so the last of several writers leaves the latest state."""
    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK, open(out_dir.parent / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        files = render(store, game)
        try:
            tomllib.loads(files["manifest.toml"].decode())
        except tomllib.TOMLDecodeError as e:
            print(f"learned manifest for {game} is not valid TOML ({e}); the previous files in {out_dir} are kept",
                  file=sys.stderr)
            return
        (out_dir / "templates").mkdir(parents=True, exist_ok=True)
        order = [r for r in files if r.startswith("templates/")] + [r for r in files if r != "manifest.toml"
                                                                    and not r.startswith("templates/")]
        for rel in order + ["manifest.toml"]:
            _put(out_dir / rel, files[rel])
        for stale in [*(out_dir / "templates").glob("*.png"), *(out_dir / n for n in PRODUCED)]:
            if stale.is_file() and stale.relative_to(out_dir).as_posix() not in files:
                stale.unlink(missing_ok=True)
