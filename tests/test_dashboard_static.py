"""Static checks of the dashboard's pages: no blocking alert(), and the serif (the model's voice) is used
only for what the model wrote (docs/design/2026-09-27-dashboard-v2-design.md, "Type" and ruling 33)."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "pilot" / "static"

# rules whose text is the model's own words: its reason, thinking, answer, stances, the strategy
# summary and plan, its Talk replies, and the stance a human edits in its place
MODEL_VOICE = {".reason", ".t-decision", ".t-reason", ".step.thinking p", ".step.text p", ".plan-text",
               ".pillar h3", ".pillar .stance", ".p-form textarea", ".msg.model p", ".s-summary"}


def css(page: str) -> str:
    text = (STATIC / page).read_text(encoding="utf-8")
    return "\n".join(re.findall(r"<style>(.*?)</style>", text, re.DOTALL))


def rules(text: str):
    """(selectors, body) of every rule, media blocks flattened."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        sel = m.group(1).strip()
        if sel.startswith("@"):
            continue
        yield [x.strip() for x in sel.split(",")], m.group(2)


def test_no_blocking_alert_in_the_pages():
    for page in ("dashboard.html", "pair.html", "signin.js"):
        assert not re.search(r"\balert\s*\(", (STATIC / page).read_text(encoding="utf-8")), page


def test_serif_is_only_the_models_voice():
    wrong = [sel for sels, body in rules(css("dashboard.html")) if "var(--serif)" in body
             for sel in sels if sel not in MODEL_VOICE]
    assert wrong == []


def test_light_text_tokens_are_the_darkened_ones():
    """Ruling 33: light-mode text tokens pass AA on plane, surface and raised."""
    root = re.search(r":root \{(.*?)\}", css("dashboard.html"), re.DOTALL).group(1)
    tokens = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-f]{6})", root))
    assert {k: tokens[k] for k in ("--muted", "--accent", "--sensor", "--warn", "--good", "--thought", "--bad")} == {
        "--muted": "#5f6271", "--accent": "#8a5a10", "--sensor": "#156f68", "--warn": "#9a4f12",
        "--good": "#1a6e3c", "--thought": "#5b43b8", "--bad": "#a82e28"}

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        x, y = sorted((lum(a), lum(b)), reverse=True)
        return (x + 0.05) / (y + 0.05)

    for fg in ("--muted", "--accent", "--sensor", "--warn", "--good", "--thought", "--bad", "--ink-2"):
        for bg in ("--plane", "--surface", "--raised"):
            assert ratio(tokens[fg], tokens[bg]) >= 4.5, (fg, bg)
    assert ratio(tokens["--accent-ink"], tokens["--accent"]) >= 4.5
