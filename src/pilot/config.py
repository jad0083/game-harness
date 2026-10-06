"""Settings: environment variables (optionally from <repo>/.env) with CLI overrides."""

from __future__ import annotations

import json
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


def _json_map(env, name: str, default: dict) -> dict:
    """A JSON object from the environment (the model guard's maps); anything else is an error naming it.
    Its values are checked by modelguard.check_guard_settings."""
    raw = env.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = json.loads(raw)
    except ValueError as e:
        raise ValueError(f"{name} is not valid JSON: {e}") from None
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object, got {type(value).__name__}")  # noqa: TRY004
    return value


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
    governor_max_requests: int = 6
    # waits between tries when the provider is overloaded or rate-limited (503/429/5xx)
    fallback_model: str | None = "google:gemini-3.1-pro-preview"   # tried once when the main model stays overloaded
    # The governor's model pool: ({"model": "provider:name", "thinking": level}, ...). Empty = the
    # model (+ fallback) above. First entry decides; the rest are tried in order when it is
    # overloaded, or, with `rotate`, each decision starts at the next entry (spreads the load).
    models: tuple = ()
    rotate: bool = False
    # Per role ("strategy", "chat", "episodes"): {"models": [...], "rotate": bool}. A role that
    # is not listed uses the decision models above.
    roles: dict = field(default_factory=dict)
    stale_save_s: float = 300.0                      # an autosave older than this at start may be another game's
    fresh_save_wait_s: float = 600.0
    model_cooldown_s: float = 600.0                  # a model that just failed goes behind the others this long
    model_timeout_s: float = 120.0                    # per model request; decisions take ~20-30 s
    retry_delays: tuple[float, ...] = (5, 15, 45)      # waits between whole-run retries on the first model (PILOT_MODEL_GUARD=0 only)
    # the model guard (docs/design/2026-10-02-model-guard-design.md, ruling 15): pacing, one short retry,
    # a breaker per model and failover inside a run; PILOT_MODEL_GUARD=0 runs the whole-run retries above
    model_guard: bool = True
    overload_retry_s: tuple[float, float] = (1.0, 2.0)
    rate_retry_max_s: float = 10.0
    breaker_open_s: float = 60.0
    breaker_max_s: float = 600.0
    pool_max_wait_s: float = 60.0
    min_call_interval_s: dict = field(default_factory=lambda: {"google": 0.5})
    model_limits: dict = field(default_factory=dict)          # model -> {rpm, tpm, daily_requests}
    model_families: dict = field(default_factory=dict)        # model -> family, over the name rule
    retro_every: int = 5                # Stellaris: a retrospective after every N model decisions (0 = never)
    image_detail: str = "medium"       # low | medium | high (Gemini media resolution)
    images_in_context: int = 2         # older screenshots in an episode become text stubs
    max_requests_per_episode: int = 30 # loop guard, not a cost limit
    turns_per_autopilot: int = 20
    game: str = "galciv4"
    runs_dir: Path = REPO / "runs"          # the data directory (PILOT_DATA_DIR; PILOT_RUNS_DIR is its alias)
    corpora_dir: Path = REPO / "corpora"
    controller_path: Path = REPO / "target/release/game-controller"
    frames_keep: int = 200                  # frames kept per run (newest first)
    export_dir: Path | None = None          # where every run exports its learned files and journal when it ends
    agent_url: str = field(default_factory=lambda: os.environ.get("GAME_AGENT_URL") or "http://127.0.0.1:8765")
    dashboard_host: str = "0.0.0.0"        # the viewer's bind address (PILOT_VIEW_HOST, `view --host`)
    dashboard_port: int = 8790             # the live pilot's own dashboard (PILOT_PORT)
    # The live pilot's dashboard answers only the viewer and scripts on this machine (ruling 36 of the
    # dashboard v2 design): loopback unless PILOT_LIVE_HOST says otherwise.
    live_host: str = "127.0.0.1"
    commit_learnings: bool = True
    ask_human_timeout_s: float = 45.0
    # Stellaris governor: game speed while the AI plays (slowest | slow | normal | fast | fastest;
    # the game is paused while the model decides), in-game months between scheduled decisions,
    # and seconds between autosave polls.
    speed: str = "normal"
    campaign: str = ""                 # campaign name for telemetry; default: from the save (GalCiv IV: terran-2329)
    decide_every_months: int = 12
    poll_s: float = 2.0
    # Civilization VI governor: turns the game's AI plays between decisions (one autoplay stretch)
    decide_every_turns: int = 5
    # turns per autoplay call: 1 = one turn at a time (urgent checks every turn); more lets the AI
    # carry multi-turn plans (settling, pantheon) without a hand-back each turn (see issues.md)
    autoplay_chunk: int = 3
    # the scripted last stand for a city about to fall (docs/design/2026-09-27-civ6-levers-design.md,
    # rulings 22-27): off until the live checklist passes; at most this many stands in a row per city
    last_stand: bool = False
    last_stand_max: int = 3
    # the Stellaris war crisis overlay (docs/design/2026-09-27-stellaris-levers-design.md, rulings
    # 12-16): on by default; PILOT_WAR_CRISIS=0 turns it off for a run
    war_crisis: bool = True

    @property
    def view_host(self) -> str:
        return self.dashboard_host

    @property
    def corpus_dir(self) -> Path:
        return self.corpora_dir / self.game

    @property
    def pillars_file(self) -> Path:
        """The game's strategy pillars (docs/design/2026-09-26-game-pillars-design.md)."""
        return self.corpus_dir / "pillars.toml"

    @property
    def db_path(self) -> Path:
        return self.runs_dir / "pilot.db"

    @property
    def frames_dir(self) -> Path:
        return self.runs_dir / "frames"

    @property
    def learned_dir(self) -> Path:
        return self.runs_dir / "learned" / self.game

    @property
    def secrets_dir(self) -> Path:
        return self.runs_dir / "secrets"

    @property
    def window_title(self) -> str:
        return {"stellaris": "Stellaris"}.get(self.game, "Galactic Civilizations")

    @property
    def controller_bin(self) -> Path:
        return self.controller_path

    def pool(self) -> list[dict]:
        """The governor's models in order, each with its thinking level."""
        if self.models:
            return [dict(m) for m in self.models]
        out = [{"model": self.model, "thinking": self.governor_thinking}]
        if self.fallback_model and self.fallback_model != self.model:
            out.append({"model": self.fallback_model, "thinking": self.governor_thinking})
        return out

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
        fb = env.get("PILOT_FALLBACK_MODEL")
        if fb is not None:
            s.fallback_model = None if fb.strip().lower() in ("", "none", "off") else fb.strip()
        s.image_detail = env.get("PILOT_IMAGE_DETAIL", s.image_detail)
        s.dashboard_port = int(env.get("PILOT_PORT", s.dashboard_port))
        s.live_host = env.get("PILOT_LIVE_HOST", s.live_host).strip() or s.live_host
        s.dashboard_host = env.get("PILOT_VIEW_HOST", s.dashboard_host).strip() or s.dashboard_host
        s.turns_per_autopilot = int(env.get("PILOT_TURNS", s.turns_per_autopilot))
        s.commit_learnings = env.get("PILOT_COMMIT", "1") not in ("0", "false", "no")
        s.game = env.get("PILOT_GAME", s.game)
        s.speed = env.get("PILOT_SPEED", s.speed)
        s.decide_every_months = int(env.get("PILOT_DECIDE_MONTHS", s.decide_every_months))
        s.poll_s = float(env.get("PILOT_POLL_S", s.poll_s))
        s.decide_every_turns = int(env.get("PILOT_DECIDE_TURNS", s.decide_every_turns))
        s.autoplay_chunk = max(1, int(env.get("PILOT_AUTOPLAY_CHUNK", s.autoplay_chunk)))
        s.last_stand = env.get("PILOT_LAST_STAND", "0").strip().lower() in ("1", "true", "yes", "on")
        s.last_stand_max = max(1, int(env.get("PILOT_LAST_STAND_MAX", s.last_stand_max)))
        s.war_crisis = env.get("PILOT_WAR_CRISIS", "1").strip().lower() not in ("0", "false", "no", "off")
        s.campaign = env.get("PILOT_CAMPAIGN", s.campaign)
        s.retro_every = int(env.get("PILOT_RETRO_EVERY", s.retro_every))
        s.model_guard = env.get("PILOT_MODEL_GUARD", "1").strip().lower() not in ("0", "false", "no", "off")
        s.min_call_interval_s = _json_map(env, "PILOT_MIN_CALL_INTERVAL", s.min_call_interval_s)
        s.model_limits = _json_map(env, "PILOT_MODEL_LIMITS", s.model_limits)
        s.model_families = _json_map(env, "PILOT_MODEL_FAMILIES", s.model_families)
        # their values are checked only when one is set (the defaults are valid), so the CLI's other
        # commands, which read the settings too, do not import the model guard
        if any(env.get(v) for v in ("PILOT_MIN_CALL_INTERVAL", "PILOT_MODEL_LIMITS", "PILOT_MODEL_FAMILIES")):
            from .modelguard import check_guard_settings

            check_guard_settings(s.min_call_interval_s, s.model_limits, s.model_families)
        data_dir = env.get("PILOT_DATA_DIR") or env.get("PILOT_RUNS_DIR")
        if data_dir:
            s.runs_dir = Path(data_dir).resolve()      # absolute: the controller and the service differ in cwd
        if env.get("PILOT_CORPORA_DIR"):
            s.corpora_dir = Path(env["PILOT_CORPORA_DIR"])
        if env.get("PILOT_CONTROLLER_BIN"):
            s.controller_path = Path(env["PILOT_CONTROLLER_BIN"])
        s.frames_keep = max(1, int(env.get("PILOT_FRAMES_KEEP", s.frames_keep)))
        if env.get("PILOT_EXPORT_DIR"):
            s.export_dir = Path(env["PILOT_EXPORT_DIR"])
        return s
