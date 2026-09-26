"""Models the pilot can switch to: Gemini models this API key can call (from the API), plus any
listed in PILOT_MODELS (comma-separated pydantic-ai model strings, e.g. "openai:gpt-5")."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import Settings

MODEL_RE = re.compile(r"^[a-z][a-z0-9-]*:[A-Za-z0-9._/:-]+$")     # provider:name
THINKING = ("off", "low", "medium", "high")
# Gemini models that cannot play: speech, image, transcription, robotics and computer-use variants
NOT_FOR_PLAY = ("tts", "image", "transcribe", "robotics", "computer-use", "embedding", "customtools")


def valid_model(name: str) -> bool:
    return bool(MODEL_RE.match(name))


def google_models() -> list[str]:
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        return []
    from google import genai

    client = genai.Client(api_key=key)
    out = []
    for m in client.models.list():
        name = (m.name or "").split("/")[-1]
        actions = getattr(m, "supported_actions", None) or []
        if name.startswith("gemini") and ("generateContent" in actions or not actions) and not any(x in name for x in NOT_FOR_PLAY):
            out.append(f"google:{name}")
    return out


# Providers the pilot can use (pydantic-ai model prefixes) and the API key each needs.
PROVIDERS = [
    {"id": "google", "label": "Google", "key_env": "GOOGLE_API_KEY", "alt_env": "GEMINI_API_KEY"},
    {"id": "anthropic", "label": "Anthropic", "key_env": "ANTHROPIC_API_KEY"},
    {"id": "openai", "label": "OpenAI", "key_env": "OPENAI_API_KEY"},
]


def provider_models(provider: str) -> list[str]:
    """Models the configured key can call for one provider ("provider:name"), from the provider's API."""
    if provider == "google":
        return google_models()
    if provider == "anthropic":
        import anthropic
        return sorted(f"anthropic:{m.id}" for m in anthropic.Anthropic().models.list(limit=100))
    if provider == "openai":
        import openai
        keep = ("gpt-", "o1", "o3", "o4", "o5")
        return sorted(f"openai:{m.id}" for m in openai.OpenAI().models.list()
                      if m.id.startswith(keep) and not any(x in m.id for x in ("audio", "realtime", "tts", "image", "transcribe", "search")))
    return []


def provider_catalog(s: Settings, list_models=provider_models) -> list[dict]:
    """Every provider with whether its API key is set and, if so, its models (plus PILOT_MODELS extras)."""
    extras = [m.strip() for m in os.environ.get("PILOT_MODELS", "").split(",") if valid_model(m.strip())]
    out = []
    for p in PROVIDERS:
        configured = bool(os.environ.get(p["key_env"]) or (p.get("alt_env") and os.environ.get(p["alt_env"])))
        models: list[str] = []
        error = ""
        if configured:
            try:
                models = list(list_models(p["id"]))
            except Exception as e:  # noqa: BLE001 - a listing failure must not hide the provider
                error = f"{type(e).__name__}: {e}"[:200]
        models += [m for m in extras if m.startswith(p["id"] + ":") and m not in models]
        out.append({"id": p["id"], "label": p["label"], "key_env": p["key_env"], "configured": configured,
                    "models": sorted(set(models)), "error": error})
    return out


def available_models(s: Settings) -> list[str]:
    models = {s.model}
    try:
        models.update(google_models())
    except Exception as e:  # noqa: BLE001 - the list is a convenience; the current model always works
        print(f"could not list Gemini models: {e}", flush=True)
    models.update(m.strip() for m in os.environ.get("PILOT_MODELS", "").split(",") if valid_model(m.strip()))
    return sorted(models)


PREFS_FILE = "pilot-settings.json"


def load_prefs(runs_dir: Path) -> dict:
    """The model and thinking level chosen on the dashboard (used by the next `pilot run`)."""
    try:
        d = json.loads((runs_dir / PREFS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    if isinstance(d.get("model"), str) and valid_model(d["model"]):
        out["model"] = d["model"]
    if d.get("thinking") in THINKING:
        out["thinking"] = d["thinking"]
    if isinstance(d.get("fallback"), str) and (d["fallback"] == "none" or valid_model(d["fallback"])):
        out["fallback"] = d["fallback"]
    if d.get("game") in GAMES:
        out["game"] = d["game"]
    if d.get("speed") in SPEEDS:
        out["speed"] = d["speed"]
    if isinstance(d.get("months"), int) and 1 <= d["months"] <= 120:
        out["months"] = d["months"]
    try:
        out["models"] = check_pool(d["models"]) if d.get("models") else None
    except ValueError:
        out["models"] = None
    if not out["models"]:
        del out["models"]
        if out.get("model"):       # settings saved before the pool: model + thinking + fallback
            th = out.get("thinking", "medium")
            pool = [{"model": out["model"], "thinking": th}]
            fb = out.get("fallback")
            if fb and fb != "none" and fb != out["model"]:
                pool.append({"model": fb, "thinking": th})
            out["models"] = pool
    if isinstance(d.get("rotate"), bool):
        out["rotate"] = d["rotate"]
    raw_roles = dict(d["roles"]) if isinstance(d.get("roles"), dict) else {}
    if "retrospective" in raw_roles and "strategy" not in raw_roles:
        raw_roles["strategy"] = raw_roles.pop("retrospective")
    raw_roles.pop("retrospective", None)
    try:
        roles = check_roles(raw_roles)
    except ValueError:
        roles = {}
    if roles:
        out["roles"] = roles
    return out


MAX_POOL = 6

# Where the pilot calls a model. "decisions" is the main list; the others use it unless given their own.
ROLES = [
    {"id": "decisions", "label": "Decisions", "help": "The standing directive, every few in-game months (Stellaris governor)."},
    {"id": "strategy", "label": "Strategy", "help": "Sets and reviews the pillar strategies at the start, every few decisions and on big events: use your best reasoning model."},
    {"id": "chat", "label": "Talk", "help": "Answers questions in the Talk tab: interactive, a fast model is enough."},
    {"id": "episodes", "label": "GC4 blockers", "help": "Galactic Civilizations IV blockers read from screenshots (needs a vision model)."},
]
ROLE_IDS = [r["id"] for r in ROLES if r["id"] != "decisions"]


def check_roles(roles) -> dict:
    """{role: {"models": [...], "rotate": bool} | None}; None or no models = use the decision models."""
    if not isinstance(roles, dict):
        raise ValueError("roles must be an object of role -> {models, rotate}")  # noqa: TRY004 - the API maps ValueError to 400
    out = {}
    for role, cfg in roles.items():
        if role not in ROLE_IDS:
            raise ValueError(f"unknown role {role!r}; roles: {', '.join(ROLE_IDS)}")
        if cfg and cfg.get("models"):
            out[role] = {"models": check_pool(cfg["models"]), "rotate": bool(cfg.get("rotate", False))}
    return out


def check_pool(models) -> list[dict]:
    """A model pool from the dashboard: 1-6 entries of {"model": "provider:name", "thinking": level}."""
    if not isinstance(models, list) or not 1 <= len(models) <= MAX_POOL:
        raise ValueError(f"the model list needs 1 to {MAX_POOL} models")
    out = []
    for m in models:
        name, th = (m or {}).get("model"), (m or {}).get("thinking", "medium")
        if not isinstance(name, str) or not valid_model(name):
            raise ValueError(f"not a model name: {name!r} (expected provider:name)")
        if th not in THINKING:
            raise ValueError(f"thinking must be one of {', '.join(THINKING)}")
        out.append({"model": name, "thinking": th})
    return out


GAMES = ("stellaris", "galciv4")
SPEEDS = ("slowest", "slow", "normal", "fast", "fastest")


def save_prefs(runs_dir: Path, model: str | None = None, thinking: str | None = None, **run: object) -> dict:
    """Merge into the saved choices: model, thinking, and run settings (game, speed, months)."""
    prefs = load_prefs(runs_dir)
    if model is not None:
        if not valid_model(model):
            raise ValueError(f"not a model name: {model!r} (expected provider:name)")
        prefs["model"] = model
    if thinking is not None:
        if thinking not in THINKING:
            raise ValueError(f"thinking must be one of {', '.join(THINKING)}")
        prefs["thinking"] = thinking
    if run.get("models") is not None:
        pool = check_pool(run["models"])
        prefs["models"] = pool
        prefs["model"], prefs["thinking"] = pool[0]["model"], pool[0]["thinking"]
    if run.get("rotate") is not None:
        prefs["rotate"] = bool(run["rotate"])
    if run.get("roles") is not None:
        merged = {**prefs.get("roles", {}), **run["roles"]}
        prefs["roles"] = check_roles({k: val for k, val in merged.items() if val})
    if run.get("fallback") is not None:
        fb = str(run["fallback"])
        if fb != "none" and not valid_model(fb):
            raise ValueError(f"fallback must be a model name (provider:name) or none, not {fb!r}")
        prefs["fallback"] = fb
    if run.get("game") is not None:
        if run["game"] not in GAMES:
            raise ValueError(f"game must be one of {', '.join(GAMES)}")
        prefs["game"] = run["game"]
    if run.get("speed") is not None:
        if run["speed"] not in SPEEDS:
            raise ValueError(f"speed must be one of {', '.join(SPEEDS)}")
        prefs["speed"] = run["speed"]
    if run.get("months") is not None:
        m = run["months"]
        if not isinstance(m, int) or not 1 <= m <= 120:
            raise ValueError("months must be a whole number from 1 to 120")
        prefs["months"] = m
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / PREFS_FILE).write_text(json.dumps(prefs, indent=1), encoding="utf-8")
    return prefs
