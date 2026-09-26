#!/usr/bin/env python3
"""Copy Stellaris definition files from the gaming PC through the agent's read-only file access
(agent >= 1.2.0, root `stellaris_install`) into a local folder for scripts/extract-stellaris.py.

    python3 scripts/fetch-stellaris-files.py                  # -> incoming/stellaris/ (gitignored)
    python3 scripts/fetch-stellaris-files.py --out /tmp/stl --dir common/technology

Files whose size and modification time match the local copy are skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_DIRS = [
    "common/technology", "common/policies", "common/edicts", "common/buildings", "common/districts",
    "common/traditions", "common/tradition_categories", "common/ascension_perks", "common/governments/civics",
    "common/scripted_variables", "common/traits", "common/planet_classes", "events", "localisation/english",
]
SKIP_DIRS = {"name_lists", "random_names"}          # localisation/english sub-folders we don't need
ROOT = "stellaris_install"


class Agent:
    def __init__(self, url: str, token: str):
        self.url, self.token = url.rstrip("/"), token

    def _get(self, endpoint: str, **q) -> urllib.request.addinfourl:
        req = urllib.request.Request(f"{self.url}{endpoint}?{urllib.parse.urlencode(q)}",
                                     headers={"Authorization": f"Bearer {self.token}"})
        return urllib.request.urlopen(req, timeout=60)  # LAN agent URL from config

    def list(self, rel: str) -> list[dict]:
        with self._get("/files/list", root=ROOT, path=rel) as r:
            return json.load(r)["entries"]

    def read(self, rel: str) -> bytes:
        with self._get("/files/read", root=ROOT, path=rel) as r:
            return r.read()


def fetch(agent: Agent, rel: str, out: Path, stats: dict) -> None:
    for e in agent.list(rel):
        child = f"{rel}/{e['name']}"
        if e["is_dir"]:
            if e["name"] not in SKIP_DIRS:
                fetch(agent, child, out, stats)
            continue
        dest = out / child
        if dest.exists() and dest.stat().st_size == e["size"] and int(dest.stat().st_mtime) == e["modified"]:
            stats["skipped"] += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = agent.read(child)
        dest.write_bytes(data)
        os.utime(dest, (e["modified"], e["modified"]))
        stats["fetched"] += 1
        stats["bytes"] += len(data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "incoming/stellaris")
    ap.add_argument("--dir", action="append", help="install-relative folder (repeatable); default: all needed")
    ap.add_argument("--agent", default=os.environ.get("GAME_AGENT_URL", "http://192.168.1.77:8765"))
    a = ap.parse_args(argv)
    token = os.environ.get("GAME_AGENT_TOKEN") or (REPO / ".agent_token").read_text().strip()
    agent = Agent(a.agent, token)
    stats = {"fetched": 0, "skipped": 0, "bytes": 0}
    for d in a.dir or DEFAULT_DIRS:
        fetch(agent, d, a.out, stats)
    # the version string lets the extractor record what it read
    (a.out / "launcher-settings.json").write_bytes(agent.read("launcher-settings.json"))
    dlc = sorted(e["name"] for e in agent.list("dlc") if e["is_dir"])
    (a.out / "dlc.json").write_text(json.dumps(dlc, indent=1))
    print(f"{stats['fetched']} fetched ({stats['bytes'] / 1e6:.1f} MB), {stats['skipped']} unchanged -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
