"""Every setting the app reads is documented for a container install (appliance image design, ruling 7)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# test-only hooks, never set by a user (PILOT_RUNS_DIR, an alias of PILOT_DATA_DIR, is mentioned there)
INTERNAL = {"PILOT_SUPERVISOR_ARGV", "PILOT_RESUME_DELAY_S",
            # constants of the code that only look like settings (not environment variables)
            "GAME_KEYS", "GAME_TITLE", "GAME_WINDOWS"}


def read_by_code() -> set[str]:
    names = set()
    for p in (ROOT / "src/pilot").glob("*.py"):
        names |= set(re.findall(r"\b((?:PILOT|GAME|LITESTREAM)_[A-Z0-9_]+|(?:GEMINI|GOOGLE|ANTHROPIC|OPENAI)_API_KEY)\b",
                                p.read_text(encoding="utf-8")))
    return names


def documented() -> set[str]:
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", (ROOT / ".env.example").read_text(), re.MULTILINE))


def test_every_setting_the_code_reads_is_in_env_example():
    missing = read_by_code() - documented() - INTERNAL
    assert not missing, sorted(missing)


def test_env_example_holds_no_values_for_secrets():
    text = (ROOT / ".env.example").read_text()
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GAME_AGENT_TOKEN",
                "PILOT_PROXY_SECRET", "PILOT_DASHBOARD_KEY", "LITESTREAM_ACCESS_KEY_ID",
                "LITESTREAM_SECRET_ACCESS_KEY"):
        assert re.search(rf"^#?\s*{key}=\s*$", text, re.MULTILINE), key


def test_compose_is_the_portable_service():
    # PyYAML is not a dependency, so the file is checked as text
    text = (ROOT / "compose.yaml").read_text()
    assert re.search(r"^\s+image: ghcr\.io/jad0083/game-pilot:", text, re.MULTILINE)
    assert re.search(r"^\s+restart: unless-stopped\s*$", text, re.MULTILINE)
    assert re.search(r"^\s+stop_grace_period: 40s\s*$", text, re.MULTILINE)
    assert re.search(r"^\s+env_file: \.env\s*$", text, re.MULTILINE)
    assert re.search(r"volumes:\s*\[?\s*[\"']?[^\n]*:/data[\"']?\s*\]?", text)
