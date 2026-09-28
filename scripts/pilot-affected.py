#!/usr/bin/env python3
"""Which services a change affects (docs/design/2026-09-27-postmortem-fixes-design.md, ruling 28): a
Stellaris-only merge restarted the live Civ VI run at T462, because one unit (game-pilot.service) runs
whichever game runs/pilot-settings.json names. scripts/deploy-pilot.sh acts on this.

    scripts/pilot-affected.py <from> <to> [--game civ6] [--running 1] [--format json|env]
    scripts/pilot-affected.py --paths src/pilot/governor.py docs/x.md --game civ6

Each changed path gets one class:

    none       docs/**, games/**, tests/**, corpora/*/learned/**, scripts/ci*, other *.md: nothing
    civ6       src/pilot/civ6*.py, corpora/civ6/** (its .md files too: the governor reads them at start)
    stellaris  src/pilot/stellaris*.py, corpora/stellaris/**
    galciv4    src/pilot/controller.py, corpora/galciv4/**
    view       src/pilot/static/**: the always-on viewer only
    rust       crates/**, Cargo.*: pause, build the controller, resume (each call runs the binary afresh)
    shared     every other src/pilot/*.py (dashboard.py too: the pilot serves its live controls with it),
               pyproject.toml, and any path not listed (the safe side)

The running pilot restarts when its game's class or `shared` is affected (any game's class when its game
is unknown); the viewer restarts for `view` and `shared` (it imports the shared modules)."""

from __future__ import annotations

import argparse
import fnmatch
import json
import shlex
import subprocess
import sys
from pathlib import Path

GAMES = ("civ6", "stellaris", "galciv4")
# first match wins: learned notes before their corpus, a corpus before the generic *.md rule
RULES = (
    ("none", ("corpora/*/learned/*",)),
    ("civ6", ("src/pilot/civ6*.py", "corpora/civ6/*")),
    ("stellaris", ("src/pilot/stellaris*.py", "corpora/stellaris/*")),
    ("galciv4", ("src/pilot/controller.py", "corpora/galciv4/*")),
    ("view", ("src/pilot/static/*",)),
    ("rust", ("crates/*", "Cargo.*")),
    ("none", ("docs/*", "games/*", "tests/*", "scripts/ci*", "*.md")),
    ("shared", ("src/pilot/*.py", "pyproject.toml")),
)


def classify(path: str) -> str:
    """The class of one changed path (fnmatch's * crosses slashes); unknown paths are shared."""
    for cls, patterns in RULES:
        if any(fnmatch.fnmatchcase(path, p) for p in patterns):
            return cls
    return "shared"


def plan(paths: list[str], game: str = "unknown", running: bool = True) -> dict:
    """What a deploy of `paths` does with a pilot of `game` (running or not)."""
    classes: dict[str, list[str]] = {}
    for p in paths:
        classes.setdefault(classify(p), []).append(p)
    pilot_classes = {"shared", game} if game in GAMES else {"shared", *GAMES}
    affected = sorted(pilot_classes & set(classes))
    restart = running and bool(affected)
    if not running:
        message = "no pilot runs: the change applies at its next start"
    elif restart:
        message = f"restart the running {game} pilot: " + ", ".join(affected) + " changed"
    else:
        message = f"not restarted: the running {game} pilot is unaffected; the change applies at its next start"
    return {"game": game, "running": running, "classes": classes, "build": "rust" in classes,
            "restart_pilot": restart, "restart_view": bool({"view", "shared"} & set(classes)), "message": message}


def changed_paths(rev_from: str, rev_to: str, cwd: Path) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", rev_from, rev_to], cwd=cwd, capture_output=True, text=True,
                         check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def _flag(v: bool) -> str:
    return "1" if v else "0"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("revs", nargs="*", help="<from> <to>: git revisions")
    ap.add_argument("--paths", nargs="+", help="classify these paths instead of a git diff")
    ap.add_argument("--game", default="unknown", help="the running pilot's game (civ6, stellaris, galciv4)")
    ap.add_argument("--running", default="1", help="1 when a pilot runs, 0 when none does")
    ap.add_argument("--format", choices=("json", "env"), default="json")
    a = ap.parse_args(argv)
    if a.paths is None and len(a.revs) != 2:
        ap.error("give <from> <to>, or --paths")
    paths = a.paths if a.paths is not None else changed_paths(*a.revs, cwd=Path(__file__).resolve().parent.parent)
    p = plan(paths, a.game, a.running not in ("0", "", "false", "no"))
    if a.format == "json":
        print(json.dumps(p, indent=1))
    else:
        for k, v in (("GAME", p["game"]), ("BUILD", _flag(p["build"])), ("RESTART_PILOT", _flag(p["restart_pilot"])),
                     ("RESTART_VIEW", _flag(p["restart_view"])), ("MESSAGE", p["message"]),
                     ("CLASSES", " ".join(f"{c}:{len(v)}" for c, v in sorted(p["classes"].items())))):
            print(f"{k}={shlex.quote(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
