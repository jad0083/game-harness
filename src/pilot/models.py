"""Models the pilot can switch to: Gemini models this API key can call (from the API), plus any
listed in PILOT_MODELS (comma-separated pydantic-ai model strings, e.g. "openai:gpt-5")."""

from __future__ import annotations

import os
import re

from .config import Settings

MODEL_RE = re.compile(r"^[a-z][a-z0-9-]*:[A-Za-z0-9._/:-]+$")     # provider:name
THINKING = ("off", "low", "medium", "high")


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
        if name.startswith("gemini") and ("generateContent" in actions or not actions) and "embedding" not in name:
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
