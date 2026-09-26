"""Settings: environment variables (optionally from <repo>/.env) with CLI overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path = REPO / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines; existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def default_journal(game: str) -> Path:
    return {"stellaris": REPO / "games/stellaris/journal.md"}.get(game, REPO / "games/terran-2329/journal.md")


@dataclass
class Settings:
    # LLM: any pydantic-ai model string, e.g. "google:gemini-3.8-flash", "openai:gpt-5",
    # "anthropic:claude-sonnet-5", "ollama:qwen3-vl" (with OLLAMA_BASE_URL).
    model: str = "google:gemini-3.8-flash"
    # Coordinate convention the model is asked to use: "norm1000" ([0,1000] on both axes,
    # what Gemini is trained on) or "pixels" (1568x882 image pixels). "auto" picks per provider.
    coords: str = "auto"
    # low | medium | high | off (provider-specific mapping). Medium by default for proper reasoning:
    # at "low", Gemini often skips thinking entirely.
    thinking: str = "medium"
    # Stellaris governor decisions (rare, strategic); set separately from GC4 episodes.
    governor_thinking: str = "medium"
    image_detail: str = "medium"       # low | medium | high (Gemini media resolution)
    images_in_context: int = 2         # older screenshots in an episode become text stubs
    max_requests_per_episode: int = 30 # loop guard, not a cost limit
    turns_per_autopilot: int = 20
    game: str = "galciv4"
    journal: Path = REPO / "games/terran-2329/journal.md"
    runs_dir: Path = REPO / "runs"
    agent_url: str = field(default_factory=lambda: os.environ.get("GAME_AGENT_URL", "http://192.168.1.77:8765"))
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8790
    commit_learnings: bool = True
    ask_human_timeout_s: float = 45.0
    # Stellaris governor: game speed while the AI plays (slowest | slow | normal | fast | fastest;
    # the game is paused while the model decides), in-game months between scheduled decisions,
    # and seconds between autosave polls.
    speed: str = "normal"
    campaign: str = ""                 # campaign name for telemetry; default: save folder / journal dir
    decide_every_months: int = 12
    poll_s: float = 2.0

    @property
    def corpus_dir(self) -> Path:
        return REPO / "corpora" / self.game

    @property
    def telemetry_db(self) -> Path:
        return self.runs_dir / "telemetry.sqlite"

    @property
    def window_title(self) -> str:
        return {"stellaris": "Stellaris"}.get(self.game, "Galactic Civilizations")

    @property
    def controller_bin(self) -> Path:
        return REPO / "target/release/game-controller"

    @property
    def provider(self) -> str:
        return self.model.split(":", 1)[0] if ":" in self.model else ""

    @property
    def coord_space(self) -> str:
        if self.coords != "auto":
            return self.coords
        return "norm1000" if self.provider in ("google", "google-cloud", "google-gla", "google-vertex") else "pixels"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        s = cls()
        env = os.environ
        s.model = env.get("PILOT_MODEL", s.model)
        s.coords = env.get("PILOT_COORDS", s.coords)
        s.thinking = env.get("PILOT_THINKING", s.thinking)
        s.governor_thinking = env.get("PILOT_GOVERNOR_THINKING", s.governor_thinking)
        s.image_detail = env.get("PILOT_IMAGE_DETAIL", s.image_detail)
        s.dashboard_port = int(env.get("PILOT_PORT", s.dashboard_port))
        s.turns_per_autopilot = int(env.get("PILOT_TURNS", s.turns_per_autopilot))
        s.commit_learnings = env.get("PILOT_COMMIT", "1") not in ("0", "false", "no")
        s.game = env.get("PILOT_GAME", s.game)
        s.speed = env.get("PILOT_SPEED", s.speed)
        s.decide_every_months = int(env.get("PILOT_DECIDE_MONTHS", s.decide_every_months))
        s.poll_s = float(env.get("PILOT_POLL_S", s.poll_s))
        s.campaign = env.get("PILOT_CAMPAIGN", s.campaign)
        if "PILOT_RUNS_DIR" in env:
            s.runs_dir = Path(env["PILOT_RUNS_DIR"])
        s.journal = default_journal(s.game)
        if "PILOT_JOURNAL" in env:
            s.journal = Path(env["PILOT_JOURNAL"])
        return s
