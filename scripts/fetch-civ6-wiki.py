#!/usr/bin/env python3
"""Fetch Civilization Wiki (Fandom) pages for corpora/civ6/docs/ through the MediaWiki API.

    python3 scripts/fetch-civ6-wiki.py            # all pages in DOCS
    python3 scripts/fetch-civ6-wiki.py loyalty    # one doc

The wiki's text is CC BY-SA 3.0; each doc keeps a Source:/License: header and nothing else is
mixed into it. "Civilopedia entry" sections (Firaxis text, not licensed for reuse) and media
sections are dropped. Wikitext is converted to plain markdown: templates such as {{Science6}}
become words, links become their labels, tables become one line per row. The live pages block
non-browser clients, but `api.php?action=parse` answers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "corpora/civ6/docs"
API = "https://civilization.fandom.com/api.php"
WIKI = "https://civilization.fandom.com/wiki/"
UA = "game-harness-corpus/1.0 (personal reference; MediaWiki API)"
LICENSE = ('License: CC BY-SA 3.0 (Civilization Wiki, Fandom: "Community content is available under '
           'CC-BY-SA unless otherwise noted.")')

# doc stem -> (title, [wiki pages])
DOCS = {
    "districts": ("Districts", ["District_(Civ6)"]),
    "adjacency": ("Adjacency bonus", ["Adjacency_bonus_(Civ6)"]),
    "victory": ("Victory", ["Victory_(Civ6)"]),
    "loyalty": ("Loyalty", ["Loyalty_(Civ6)"]),
    "ages_era_score": ("Ages and era score", ["Age_(Civ6)", "Historic_Moment_(Civ6)"]),
    "diplomacy": ("Diplomacy, grievances and casus belli", ["Diplomacy_(Civ6)", "Grievances_(Civ6)",
                                                            "Casus_Belli_(Civ6)"]),
    "world_congress": ("World Congress, diplomatic favor and emergencies",
                       ["World_Congress_(Civ6)", "Diplomatic_Favor_(Civ6)", "Emergency_(Civ6)"]),
    "ai_agendas": ("AI agendas", ["List_of_agendas_in_Civ6"]),
    "difficulty": ("Difficulty levels", ["Difficulty_level_(Civ6)"]),
    "combat": ("Combat", ["Combat_(Civ6)"]),
    "great_people": ("Great People", ["Great_People_(Civ6)"]),
    "trade_routes": ("Trade routes", ["Trade_Route_(Civ6)"]),
    "climate": ("Climate", ["Climate_(Civ6)"]),
}

DROP_SECTIONS = re.compile(r"^(civilopedia entry|gallery|videos?|related achievements|see also|external links|"
                           r"references|notes and references|trivia)$", re.IGNORECASE)
# Link-style templates whose last positional argument is the label ({{Link6|Campus}}).
LINK_TEMPLATES = {"link6", "link", "civ6link", "l6", "c6"}


def fetch(page: str) -> tuple[str, int, str]:
    q = urllib.parse.urlencode({"action": "parse", "page": page, "prop": "wikitext|revid", "format": "json",
                                "formatversion": "2", "redirects": "1"})
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "error" in d:
        raise RuntimeError(f"{page}: {d['error'].get('info')}")
    p = d["parse"]
    return p["wikitext"], p.get("revid", 0), p["title"]


def _template(body: str) -> str:
    parts = [p.strip() for p in body.split("|")]
    name = parts[0].strip()
    low = name.lower().replace(" ", "")
    positional = [p for p in parts[1:] if "=" not in p]
    if low in LINK_TEMPLATES and positional:
        return positional[-1]
    if not positional and re.fullmatch(r"[A-Za-z]+6", name):          # {{Science6}} -> Science
        words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name[:-1])
        return words
    return ""


def strip_templates(s: str) -> str:
    for _ in range(12):                       # innermost first, templates nest
        s2 = re.sub(r"\{\{([^{}]*)\}\}", lambda m: _template(m.group(1)), s)
        if s2 == s:
            break
        s = s2
    return s


def link(m: re.Match) -> str:
    target, _, label = m.group(1).partition("|")
    if re.match(r"(?i)(file|image|category|media):", target):
        return ""
    label = label or target
    return re.sub(r"\s*\((Civ6|Civilization VI)\)", "", label.split("|")[-1]).strip()


def table(block: str) -> str:
    rows, cur = [], []
    for line in block.splitlines()[1:]:
        t = line.strip()
        if t.startswith("|}"):
            break
        if t.startswith("|-"):
            if cur:
                rows.append(cur)
            cur = []
            continue
        if t.startswith("|+"):
            continue
        if t.startswith(("!", "|")):
            cells = re.split(r"\|\||!!", t[1:])
            for c in cells:
                c = c.split("|", 1)[-1] if re.match(r'^\s*[a-z-]+\s*=\s*"', c) else c
                cur.append(c.strip())
        elif cur:
            cur[-1] += " " + t
    if cur:
        rows.append(cur)
    return "\n".join("- " + " | ".join(c for c in r if c) for r in rows if any(r))


def convert(wt: str) -> str:
    s = re.sub(r"<!--.*?-->", "", wt, flags=re.DOTALL)
    s = re.sub(r"<ref[^>/]*/>", "", s)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.DOTALL)
    s = strip_templates(s)
    s = re.sub(r"\{\|.*?\n\|\}", lambda m: table(m.group(0)), s, flags=re.DOTALL)
    for _ in range(3):                        # file captions contain links: [[File:x|thumb|[[A|a]]]]
        s = re.sub(r"\[\[([^\[\]]*)\]\]", link, s)
    s = re.sub(r"\[https?://\S+ ([^\]]+)\]", r"\1", s)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"</?[a-zA-Z][^>]*>", "", s)
    s = s.replace("'''", "**").replace("''", "")
    out, skip_level = [], 0
    for line in s.splitlines():
        h = re.match(r"^(=+)\s*(.*?)\s*=+\s*$", line)
        if h:
            level = len(h.group(1))
            if skip_level and level > skip_level:
                continue
            skip_level = 0
            if DROP_SECTIONS.match(h.group(2).strip("* ")):
                skip_level = level
                continue
            out.append("\n" + "#" * min(level, 4) + " " + h.group(2).strip("* ").strip())
            continue
        if skip_level:
            continue
        line = re.sub(r"^\*+\s*", "- ", line)
        line = re.sub(r"^#+\s*", "1. ", line)
        line = re.sub(r"^:+\s*", "", line)
        line = re.sub(r"^;\s*", "", line)
        out.append(line.rstrip())
    text = "\n".join(out)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_doc(stem: str, pause: float = 1.0) -> str:
    title, pages = DOCS[stem]
    parts, sources, revs = [], [], []
    for i, page in enumerate(pages):
        if i:
            time.sleep(pause)
        wt, rev, real = fetch(page)
        sources.append(WIKI + real.replace(" ", "_"))
        revs.append(f"{real} rev {rev}")
        body = convert(wt)
        parts.append((f"## {real}\n\n" if len(pages) > 1 else "") + body)
    head = [f"# {title} (Civilization VI)", f"Source: {sources[0]}", *[f"- {u}" for u in sources[1:]], LICENSE, ""]
    note = (f"_Retrieved {time.strftime('%Y-%m-%d')} through the wiki's MediaWiki API ({'; '.join(revs)}). "
            "Wiki prose may predate Gathering Storm balance changes; the generated records in ../data "
            "(the game's own files, 1.0.12.68) win where numbers differ._")
    return "\n".join(head) + "\n" + note + "\n\n" + "\n\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docs", nargs="*", help=f"doc stems (default: all of {', '.join(DOCS)})")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    for i, stem in enumerate(a.docs or list(DOCS)):
        if i:
            time.sleep(1.0)
        text = build_doc(stem)
        (a.out / f"{stem}.md").write_text(text, encoding="utf-8")
        print(f"{stem}.md: {len(text):,} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
