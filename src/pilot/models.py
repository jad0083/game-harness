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
    return out


def save_prefs(runs_dir: Path, model: str, thinking: str) -> dict:
    if not valid_model(model):
        raise ValueError(f"not a model name: {model!r} (expected provider:name)")
    if thinking not in THINKING:
        raise ValueError(f"thinking must be one of {', '.join(THINKING)}")
    runs_dir.mkdir(parents=True, exist_ok=True)
    prefs = {"model": model, "thinking": thinking}
    (runs_dir / PREFS_FILE).write_text(json.dumps(prefs, indent=1), encoding="utf-8")
    return prefs
