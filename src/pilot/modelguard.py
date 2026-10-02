"""Model guard (docs/design/2026-10-02-model-guard-design.md): every model request is paced, a failure is
classified and retried at most once, and each model has a circuit breaker; a role's models form a pool
that moves a failed request to the next model with the run's history, so tools that already ran do not
run again. Nothing game-specific lives here."""

from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anyio
import httpx

PACIFIC = ZoneInfo("America/Los_Angeles")        # Gemini daily quotas reset at midnight Pacific

OVERLOADED, TIMEOUT, RATE_LIMITED, DAILY_QUOTA = "overloaded", "timeout", "rate_limited", "daily_quota"
BROKEN, REJECTED, OTHER = "broken", "rejected", "other"
CAUTION = frozenset({OVERLOADED, TIMEOUT})       # kinds that put the model's family behind the others (ruling 9)
LABEL = {OVERLOADED: "overloaded", TIMEOUT: "timed out", RATE_LIMITED: "rate limited", DAILY_QUOTA: "daily quota",
         BROKEN: "unusable", REJECTED: "request rejected", OTHER: "failed"}
USAGE_DAYS = 7                                   # days of request counts kept in the usage file (ruling 14)

_sleep = anyio.sleep                             # the guard's waits; tests replace both (tests/conftest.py)
_uniform = random.uniform


@dataclass(frozen=True)
class Failure:
    """One classified model failure (ruling 6)."""
    kind: str
    status: int | None = None
    retry_after: float | None = None             # seconds, from RetryInfo or Retry-After (429 only)
    cause: str = ""                              # one line for logs


def describe(f: Failure) -> str:
    """The failure in a few words, as the dashboard shows it: "overloaded (503)", "timed out"."""
    return LABEL.get(f.kind, f.kind) + (f" ({f.status})" if f.status else "")


def event_error(model: str, f: Failure) -> str:
    """The `error` text of model_retry and model_fallback events, in the form the dashboard already reads
    ("model gemini-3.8-flash answered 503"; ruling 21)."""
    short = model.split(":", 1)[-1]
    if f.status:
        return f"model {short} answered {f.status}" + (" (daily quota)" if f.kind == DAILY_QUOTA else "")
    return f"model {short} {f.cause or LABEL.get(f.kind, f.kind)}"


def _body(body) -> dict:
    if isinstance(body, dict):
        return body
    if isinstance(body, (str, bytes)):
        try:
            d = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return {}
        return d if isinstance(d, dict) else {}
    return {}


def _details(body) -> list[dict]:
    d = _body(body)
    err = d.get("error", d)
    det = err.get("details") if isinstance(err, dict) else None
    return [x for x in det if isinstance(x, dict)] if isinstance(det, list) else []


def _seconds(text) -> float | None:
    """A protobuf Duration ("37s", "1.5s") or a Retry-After header ("12") in seconds."""
    m = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)s?\s*", str(text or ""))
    return float(m.group(1)) if m else None


def classify(e: BaseException) -> Failure:
    """Ruling 6: what kind of failure an exception from a model request is."""
    from pydantic_ai.exceptions import ModelHTTPError
    if isinstance(e, ModelHTTPError):
        st, cause = e.status_code, f"{e.model_name} answered {e.status_code}"
        if st == 429:
            details = _details(e.body)
            quotas = [str(v.get("quotaId", "")) for x in details
                      for v in (x.get("violations") if isinstance(x.get("violations"), list) else [])
                      if isinstance(v, dict)]
            if any("PerDay" in q for q in quotas):
                return Failure(DAILY_QUOTA, st, None, cause + " (daily quota)")
            after = next((_seconds(x.get("retryDelay")) for x in details if "RetryInfo" in str(x.get("@type", ""))), None)
            if after is None and getattr(e, "headers", None):
                after = _seconds(e.headers.get("retry-after"))
            return Failure(RATE_LIMITED, st, after, cause)
        if st in (500, 502, 503, 504, 529):
            return Failure(OVERLOADED, st, None, cause)
        if st in (401, 403, 404):
            return Failure(BROKEN, st, None, cause)
        if st in (400, 422):
            return Failure(REJECTED, st, None, cause)
        return Failure(OTHER, st, None, cause)
    if isinstance(e, (httpx.TimeoutException, TimeoutError)):
        return Failure(TIMEOUT, None, None, f"timed out ({type(e).__name__})")
    if isinstance(e, (httpx.ConnectError, httpx.RemoteProtocolError, ConnectionError)):
        return Failure(OVERLOADED, None, None, f"connection failed ({type(e).__name__})")
    return Failure(OTHER, None, None, f"{type(e).__name__}: {e}"[:200])


def provider(model: str) -> str:
    return model.split(":", 1)[0] if ":" in model else ""


def family(model: str, overrides: Mapping[str, str] | None = None) -> str:
    """Ruling 3: models that share capacity fail together, so a failover goes to another family."""
    if overrides and model in overrides:
        return overrides[model]
    prov, name = provider(model), model.split(":", 1)[-1].lower()
    if prov in ("anthropic", "claude-code") or name.startswith("claude"):
        return "claude"
    if prov.startswith("google") or name.startswith("gemini"):
        for key, fam in (("flash-lite", "gemini-flash-lite"), ("flash", "gemini-flash"), ("pro", "gemini-pro")):
            if key in name:
                return fam
        return "gemini"
    return prov or name


def pacific_day(now: float) -> str:
    return datetime.fromtimestamp(now, PACIFIC).date().isoformat()


def next_pacific_midnight(now: float) -> float:
    """When Gemini's daily quotas reset after `now` (ruling 7)."""
    d = datetime.fromtimestamp(now, PACIFIC).date() + timedelta(days=1)
    return datetime(d.year, d.month, d.day, tzinfo=PACIFIC).timestamp()


@dataclass
class GuardConfig:
    """Ruling 15's settings, as the guard uses them."""
    overload_retry_s: tuple[float, float] = (1.0, 2.0)
    rate_retry_max_s: float = 10.0
    breaker_open_s: float = 60.0
    breaker_max_s: float = 600.0
    pool_max_wait_s: float = 60.0
    min_call_interval_s: dict = field(default_factory=lambda: {"google": 0.5})
    model_limits: dict = field(default_factory=dict)
    model_families: dict = field(default_factory=dict)
    usage_file: Path | None = None

    @classmethod
    def from_settings(cls, s) -> GuardConfig:
        return cls(overload_retry_s=tuple(s.overload_retry_s), rate_retry_max_s=s.rate_retry_max_s,
                   breaker_open_s=s.breaker_open_s, breaker_max_s=s.breaker_max_s, pool_max_wait_s=s.pool_max_wait_s,
                   min_call_interval_s=dict(s.min_call_interval_s), model_limits=dict(s.model_limits),
                   model_families=dict(s.model_families), usage_file=Path(s.runs_dir) / "model-usage.json")


def retry_delay(f: Failure, trial: bool, cfg: GuardConfig, uniform=random.uniform) -> float | None:
    """Ruling 7: seconds before the one retry on the same model, or None for no retry."""
    if f.kind == OVERLOADED and not trial:
        return uniform(*cfg.overload_retry_s)
    if f.kind == RATE_LIMITED and f.retry_after is not None and f.retry_after <= cfg.rate_retry_max_s:
        return f.retry_after + uniform(0.0, 1.0)
    return None


@dataclass
class Breaker:
    state: str = "closed"            # closed | open | half_open | broken (ruling 2)
    until: float = 0.0
    openings: int = 0                # consecutive openings: the window doubles with each (ruling 8)
    reason: str = ""
    kind: str = ""


class ModelHealth:
    """Ruling 2: the guard's state for every model, one per pilot process, shared by every role and thread.
    `on_change(model, snap)` and `on_note(text)` are called outside the lock; `on_note` must not call back."""

    def __init__(self, config: GuardConfig, clock: Callable[[], float] = time.time,
                 on_change: Callable[[str, dict], None] | None = None, on_note: Callable[[str], None] | None = None):
        self.cfg, self.clock, self.on_change, self.on_note = config, clock, on_change, on_note
        self._lock = threading.Lock()
        self._b: dict[str, Breaker] = {}
        self._last_start: dict[str, float] = {}      # pacing: latest reserved start per model and per "provider:"
        self._tokens: dict[str, int] = {}            # input tokens of each model's last answered request
        self._days: dict[str, dict[str, int]] = {}
        self._day = pacific_day(self.clock())
        self._save_failed = False
        self._load()

    def family(self, model: str) -> str:
        return family(model, self.cfg.model_families)

    # ---- breakers (rulings 7-9) ------------------------------------------------------------------

    def status(self, model: str) -> str:
        """closed, open, trial (its window ended: the next request is its one trial), half_open (the
        trial is running) or broken."""
        with self._lock:
            return self._status(model, self.clock())

    def _status(self, model: str, now: float) -> str:
        b = self._b.get(model)
        if b is None or b.state == "closed":
            return "closed"
        if b.state == "open" and now >= b.until:
            return "trial"
        return b.state

    def begin_trial(self, model: str) -> bool:
        """Take the model's single trial (ruling 8); False when none is due or another is running."""
        with self._lock:
            now = self.clock()
            if self._status(model, now) != "trial":
                return False
            self._b[model].state = "half_open"
            snap = self._snap(model, now)
        self._notify(model, snap)
        return True

    def abandon_trial(self, model: str) -> None:
        """A trial that ended without an answer or a failure (cancelled): due again."""
        with self._lock:
            b = self._b.get(model)
            if b is not None and b.state == "half_open":
                b.state, b.until = "open", self.clock()

    def succeeded(self, model: str, input_tokens: int | None = None) -> None:
        with self._lock:
            if input_tokens:
                self._tokens[model] = int(input_tokens)
            b = self._b.pop(model, None)
            snap = self._snap(model, self.clock()) if b is not None else None
        if snap:
            self._notify(model, snap)

    def failed(self, model: str, f: Failure, reason: str | None = None) -> None:
        """Rulings 7-8: open with the doubling window, open until midnight Pacific, or mark broken; a
        rejected request changes nothing."""
        if f.kind == REJECTED:
            return
        with self._lock:
            now = self.clock()
            b = self._b.setdefault(model, Breaker())
            if f.kind == BROKEN:
                b.state, b.until = "broken", math.inf
            elif f.kind == DAILY_QUOTA:
                b.state, b.until = "open", next_pacific_midnight(now)
            else:
                b.openings += 1
                window = min(self.cfg.breaker_open_s * 2 ** (b.openings - 1), self.cfg.breaker_max_s)
                if f.kind == RATE_LIMITED:
                    window = max(window, f.retry_after or 0.0)
                b.state, b.until = "open", now + window
            b.reason, b.kind = reason or describe(f), f.kind
            snap = self._snap(model, now)
        self._notify(model, snap)

    def cautioned(self, model: str) -> bool:
        """Another model of its family is open after an overload or a timeout (ruling 9)."""
        with self._lock:
            return self._cautioned(model, self.clock())

    def _cautioned(self, model: str, now: float) -> bool:
        fam = self.family(model)
        return any(m != model and b.state == "open" and b.until > now and b.kind in CAUTION and self.family(m) == fam
                   for m, b in self._b.items())

    def earliest_reopen(self, models: Iterable[str]) -> float | None:
        """When the first of these open models is due for its trial (ruling 11)."""
        with self._lock:
            ends = [self._b[m].until for m in models if m in self._b and self._b[m].state == "open"]
        return min(ends) if ends else None

    def clear_broken(self, models: Iterable[str]) -> None:
        changed = []
        with self._lock:
            for m in set(models):
                if m in self._b and self._b[m].state == "broken":
                    del self._b[m]
                    changed.append((m, self._snap(m, self.clock())))
        for m, snap in changed:
            self._notify(m, snap)

    # ---- pacing and counts (rulings 12-14) -----------------------------------------------------

    def reserve(self, model: str) -> float:
        """Take the next start slot for a request to `model`; the seconds to wait before sending it."""
        with self._lock:
            now = self.clock()
            prov = provider(model) + ":"
            floor = float(self.cfg.min_call_interval_s.get(provider(model), 0.0))
            start = max(now, self._last_start.get(prov, -math.inf) + floor,
                        self._last_start.get(model, -math.inf) + self._gap(model))
            self._last_start[prov] = self._last_start[model] = start
            return max(0.0, start - now)

    def _gap(self, model: str) -> float:
        lim = self.cfg.model_limits.get(model) or {}
        gap = 60.0 / float(lim["rpm"]) if lim.get("rpm") else 0.0
        if lim.get("tpm") and self._tokens.get(model):
            gap = max(gap, 60.0 * self._tokens[model] / float(lim["tpm"]))
        return gap

    def count(self, model: str) -> Failure | None:
        """Count a request about to be sent. When the model's daily budget is already spent nothing is
        counted, its breaker opens until midnight Pacific and the failure is returned (ruling 13)."""
        budget = (self.cfg.model_limits.get(model) or {}).get("daily_requests")
        with self._lock:
            self._roll(self.clock())
            today = self._days.setdefault(self._day, {})
            if not budget or today.get(model, 0) < int(budget):
                today[model] = today.get(model, 0) + 1
                notes = self._save()
                over = None
            else:
                notes = []
                over = Failure(DAILY_QUOTA, None, None, f"daily budget of {int(budget)} requests reached")
        for n in notes:
            self._note(n)
        if over is not None:
            self.failed(model, over, reason="daily budget")
        return over

    def today(self, model: str) -> int:
        with self._lock:
            self._roll(self.clock())
            return self._days.get(self._day, {}).get(model, 0)

    def _roll(self, now: float) -> None:
        self._day = pacific_day(now)

    def _load(self) -> None:
        p = self.cfg.usage_file
        if p is None or not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._days = {str(d): {str(m): int(n) for m, n in c.items()} for d, c in data.items()}
        except (OSError, ValueError, TypeError, AttributeError) as e:
            self._days = {}
            self._note(f"model usage file {p.name} unreadable ({type(e).__name__}); today's counts start at 0")

    def _save(self) -> list[str]:
        """Write the counts (under the lock); returns a note to give after releasing it."""
        p = self.cfg.usage_file
        if p is None:
            return []
        oldest = (datetime.fromisoformat(self._day) - timedelta(days=USAGE_DAYS - 1)).date().isoformat()
        self._days = {d: c for d, c in self._days.items() if d >= oldest}
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(self._days, sort_keys=True), encoding="utf-8")
            os.replace(tmp, p)
        except OSError as e:
            if not self._save_failed:
                self._save_failed = True
                return [f"model usage file {p.name} not written ({type(e).__name__}); counts kept in memory"]
        return []

    # ---- what the dashboard reads (ruling 23) --------------------------------------------------

    def snapshot(self) -> dict:
        """Every model the guard has seen: its breaker, its family's caution and today's requests."""
        with self._lock:
            now = self.clock()
            self._roll(now)
            today = self._days.get(self._day, {})
            names = sorted(set(self._b) | set(today))
            return {"day": self._day, "models": {m: {**self._snap(m, now), "today": today.get(m, 0)} for m in names}}

    def _snap(self, model: str, now: float) -> dict:
        b = self._b.get(model) or Breaker()
        state = self._status(model, now)
        return {"state": state, "until": round(b.until, 1) if state == "open" else None, "reason": b.reason,
                "openings": b.openings, "family": self.family(model), "caution": self._cautioned(model, now)}

    def _notify(self, model: str, snap: dict) -> None:
        if self.on_change:
            self.on_change(model, snap)

    def _note(self, text: str) -> None:
        if self.on_note:
            self.on_note(text)
