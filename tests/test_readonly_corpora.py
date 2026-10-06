"""The corpora directory can be read-only (data platform design, ruling 3): a governor decision
writes only into the data directory."""

from __future__ import annotations

import os
import shutil
import stat

import pytest
from test_civ6_governor import FIXTURE, INDEX, governor, orders_model

from pilot.civ6 import FakeCiv6
from pilot.config import REPO, Settings
from pilot.events import EventLog

COPIED = ("pilot.md", "strategy.md", "pillars.toml", "manifest.toml", "dashboard.toml", "popups.toml")
WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


def listing(root):
    out = {}
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            p = os.path.join(d, n)
            st = os.stat(p)
            out[p] = (st.st_mtime_ns, st.st_size)
    return out


def set_writable(root, writable: bool):
    paths = [root]
    for d, dirs, files in os.walk(root):
        paths += [os.path.join(d, n) for n in dirs + files]
    for p in paths:
        mode = os.stat(p).st_mode
        os.chmod(p, mode | stat.S_IWUSR if writable else mode & ~WRITE_BITS)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores write bits")
def test_a_decision_runs_with_a_read_only_corpora_directory(tmp_path):
    corpus = tmp_path / "corpora/civ6"
    corpus.mkdir(parents=True)
    for f in COPIED:
        if (REPO / "corpora/civ6" / f).exists():
            shutil.copy(REPO / "corpora/civ6" / f, corpus / f)
    shutil.copytree(REPO / "corpora/civ6/data", corpus / "data")
    shutil.copytree(REPO / "corpora/civ6/lua", corpus / "lua")
    root = tmp_path / "corpora"
    set_writable(root, False)
    try:
        before = listing(root)
        s = Settings(model="google:gemini-3.8-flash", corpora_dir=root, runs_dir=tmp_path / "data",
                     game="civ6", decide_every_turns=3, poll_s=0, retro_every=0,
                     ask_human_timeout_s=0.05, fallback_model=None, autoplay_chunk=1)
        setup = (s, EventLog(s.runs_dir, "civ1", s.model))
        game = FakeCiv6(FIXTURE, index=INDEX)
        g = governor(setup, game, orders_model([{"kind": "research", "id": "tech:pottery"}], []))
        g.run(max_decisions=2)
        assert [a for a in game.actions if a[0] == "order"], "the decision ran"
        assert listing(root) == before
        assert (tmp_path / "data/learned/civ6/manifest.toml").exists()
    finally:
        set_writable(root, True)
