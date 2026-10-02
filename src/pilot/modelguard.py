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
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anyio
import httpx
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import merge_model_settings

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


# ---- models (rulings 4-5, 10-11, 16) ------------------------------------------------------------

class ModelUnavailable(Exception):
    """A model could not answer this request (ruling 4); the pool moves the request on."""

    def __init__(self, model: str, failure: Failure):
        super().__init__(f"{model}: {failure.cause or describe(failure)}")
        self.model, self.failure = model, failure


class PoolExhausted(Exception):
    """No model of a pool could answer a request (ruling 11)."""

    def __init__(self, role: str, tried: list[ModelUnavailable], skipped: list[str]):
        self.role, self.tried, self.skipped = role, list(tried), list(skipped)

        def part(u: ModelUnavailable) -> str:    # a failure without an HTTP status adds its own text
            f = u.failure
            return f"{u.model} {describe(f)}" + (f": {f.cause}" if f.cause and not f.status else "")
        super().__init__(f"no model could answer ({role}): " + "; ".join(
            [part(u) for u in self.tried] + [f"{m} skipped" for m in self.skipped]))

    def causes(self) -> list[dict]:
        return ([{"model": u.model, "error": describe(u.failure)} for u in self.tried]
                + [{"model": m, "error": "skipped"} for m in self.skipped])


def _noop(**_kw) -> None:
    return None


@dataclass
class Hooks:
    """What a pool reports to its owner, which writes the events (rulings 17, 21-22). All take keyword
    arguments: on_try(name, attempt, of, after=[(name, Failure)], skipped=[name]); on_retry(name, failure,
    delay, attempt, request); on_fallback(name, failure, next, request); on_pace(name, waited)."""
    on_try: Callable[..., None] = _noop
    on_retry: Callable[..., None] = _noop
    on_fallback: Callable[..., None] = _noop
    on_pace: Callable[..., None] = _noop


def event_hooks(emit, role: str, family: Callable[[str], str], extra: Hooks | None = None) -> Hooks:
    """Hooks that write model_retry, model_fallback and model_pace through `emit(kind, **data)` (rulings
    21-22), after calling `extra`'s."""
    x = extra or Hooks()

    def on_retry(name, failure, delay, attempt, request):
        x.on_retry(name=name, failure=failure, delay=delay, attempt=attempt, request=request)
        emit("model_retry", error=event_error(name, failure), delay=delay, attempt=attempt, role=role, model=name,
             failure=failure.kind, family=family(name), request=request)

    def on_fallback(name, failure, next, request):
        x.on_fallback(name=name, failure=failure, next=next, request=request)
        emit("model_fallback", role=role, model=name, error=event_error(name, failure), fallback=next,
             failure=failure.kind, family=family(name), request=request)

    def on_pace(name, waited):
        x.on_pace(name=name, waited=waited)
        emit("model_pace", model=name, waited_s=waited, role=role)
    return Hooks(on_try=x.on_try, on_retry=on_retry, on_fallback=on_fallback, on_pace=on_pace)


def emit_breaker(emit, model: str, snap: dict) -> None:
    """The model_breaker event for one breaker change (ruling 22)."""
    emit("model_breaker", model=model, family=snap["family"], state=snap["state"], until=snap["until"],
         reason=snap["reason"], openings=snap["openings"])


def build_model(name: str) -> Model:
    """A pool entry's provider model with the SDK's own retries off (ruling 16): google-genai never
    retries without retry_options, which pydantic-ai leaves unset; Anthropic's client gets max_retries=0."""
    from pydantic_ai.models import infer_model

    from .claude_code import resolve_model
    m = resolve_model(name)
    if not isinstance(m, str):
        return m
    prov, _, model_name = name.partition(":")
    if prov == "anthropic":
        from anthropic import AsyncAnthropic
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider
        return AnthropicModel(model_name, provider=AnthropicProvider(
            anthropic_client=AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"), max_retries=0)))
    return infer_model(name)


class GuardedModel(WrapperModel):
    """Ruling 4: one pool entry. It is built on first use, so a model that cannot be built (a missing key,
    an unknown provider) is marked broken instead of breaking its role."""

    def __init__(self, model: Model | str, name: str, health: ModelHealth, settings=None):
        Model.__init__(self)                     # not WrapperModel's, which builds the model at once
        self._source = model
        self._built: Model | None = model if isinstance(model, Model) else None
        self._entered = False
        self.name, self.health, self.entry_settings = name, health, settings
        self.hooks = Hooks()
        self.request_no = 0                      # set by the pool: the request's number in its run

    @property
    def wrapped(self) -> Model:  # type: ignore[override]
        if self._built is None:
            self._built = build_model(self._source)
        return self._built

    def __repr__(self) -> str:
        return f"GuardedModel({self.name!r})"

    @property
    def model_name(self) -> str:
        return self._built.model_name if self._built is not None else self.name.split(":", 1)[-1]

    @property
    def system(self) -> str:
        return self._built.system if self._built is not None else provider(self.name)

    @property
    def model_id(self) -> str:
        return self._built.model_id if self._built is not None else self.name

    def ensure_built(self) -> None:
        try:
            _ = self.wrapped
        except Exception as e:
            f = Failure(BROKEN, None, None, f"cannot be built: {type(e).__name__}: {e}"[:200])
            self.health.failed(self.name, f)
            raise ModelUnavailable(self.name, f) from e

    async def __aenter__(self):
        try:
            self.ensure_built()
            await self.wrapped.__aenter__()
            self._entered = True
        except ModelUnavailable:
            pass                                 # marked broken; the pool skips it
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._entered:
            self._entered = False
            return await self.wrapped.__aexit__(exc_type, exc_val, exc_tb)
        return None

    async def request(self, messages, model_settings, model_request_parameters):
        self.ensure_built()
        settings = merge_model_settings(model_settings, self.entry_settings)
        trial = self.health.begin_trial(self.name)
        retried = resolved = False               # resolved: succeeded() or failed() recorded the trial's verdict
        try:
            while True:
                wait = self.health.reserve(self.name)
                if wait >= 1.0:
                    self.hooks.on_pace(name=self.name, waited=round(wait, 1))
                if wait > 0:
                    await _sleep(wait)
                over = self.health.count(self.name)
                if over is not None:
                    raise ModelUnavailable(self.name, over)
                try:
                    response = await self.wrapped.request(messages, settings, model_request_parameters)
                except UsageLimitExceeded:
                    raise
                except Exception as e:
                    f = classify(e)
                    delay = None if retried else retry_delay(f, trial, self.health.cfg, _uniform)
                    if delay is None:
                        self.health.failed(self.name, f)
                        resolved = f.kind != REJECTED
                        raise ModelUnavailable(self.name, f) from e
                    retried = True
                    self.hooks.on_retry(name=self.name, failure=f, delay=round(delay, 1), attempt=1,
                                        request=self.request_no)
                    await _sleep(delay)
                    continue
                self.health.succeeded(self.name, response.usage.input_tokens)
                resolved = True
                return response
        finally:
            if trial and not resolved:
                self.health.abandon_trial(self.name)     # no verdict (rejected, cancelled, raised): due again

    @asynccontextmanager
    async def request_stream(self, *args, **kwargs):
        raise NotImplementedError("the pilot does not stream model responses")
        yield  # pragma: no cover


class PoolModel(FallbackModel):
    """Ruling 5: a role's models. Each request goes to the first model that can take it, in ruling 10's
    order; a ModelUnavailable moves the same messages (the run's history so far) to the next model, so
    the run continues and tools that already ran are not run again."""

    def __init__(self, role: str, models: list[GuardedModel], health: ModelHealth):
        super().__init__(models[0], *models[1:], fallback_on=(ModelUnavailable,))
        self.role, self.guarded, self.health = role, list(models), health
        self.hooks = Hooks()
        self._order = list(range(len(models)))
        self.requests = 0
        self.last_answered: int | None = None    # the entry that answered the run's latest request

    def begin_run(self, start: int = 0, hooks: Hooks | None = None) -> None:
        """A new run: the configured order from entry `start` (the rotation), kept for every request of
        the run (ruling 10), and the hooks that report it."""
        n = len(self.guarded)
        self._order = [(start + i) % n for i in range(n)]
        self.requests, self.last_answered = 0, None
        if hooks is not None:
            self.hooks = hooks
            for gm in self.guarded:
                gm.hooks = hooks

    def ordered(self, exclude=frozenset()) -> tuple[list[int], list[str]]:
        """This request's entries (ruling 10): the run's order without open, half-open and broken models,
        and closed models of a family under caution after the others; plus the names skipped."""
        first, later, skipped = [], [], []
        for i in self._order:
            if i in exclude:
                continue
            name = self.guarded[i].name
            state = self.health.status(name)
            if state in ("open", "half_open", "broken"):
                skipped.append(name)
            elif state == "closed" and self.health.cautioned(name):
                later.append(i)
            else:
                first.append(i)
        return first + later, skipped

    async def request(self, messages, model_settings, model_request_parameters):
        self.requests += 1
        tried: list[ModelUnavailable] = []
        done: set[int] = set()
        waited = False
        while True:
            order, skipped = self.ordered(done)     # again after every failure: a failed family moves back (ruling 9)
            if not order:
                rest = [self.guarded[i].name for i in self._order if i not in done]
                reopen = self.health.earliest_reopen(rest + [u.model for u in tried])
                now = self.health.clock()
                if waited or reopen is None or reopen - now > self.health.cfg.pool_max_wait_s:
                    raise PoolExhausted(self.role, tried, rest)
                waited = True                       # ruling 11: wait for the earliest window, once
                await _sleep(max(0.0, reopen - now))
                done = {i for i in done if self.health.status(self.guarded[i].name) != "trial"}
                continue
            i = order[0]
            gm = self.guarded[i]
            done.add(i)
            self.hooks.on_try(name=gm.name, attempt=len(tried) + 1, of=len(self.guarded),
                              after=[(u.model, u.failure) for u in tried], skipped=skipped)
            gm.request_no = self.requests
            try:
                gm.ensure_built()
                prepared = gm.prepare_messages(messages, model_request_parameters)
                response = await gm.request(prepared, model_settings, model_request_parameters)
            except ModelUnavailable as u:
                tried.append(u)
                nxt, _ = self.ordered(done)
                self.hooks.on_fallback(name=gm.name, failure=u.failure,
                                       next=self.guarded[nxt[0]].name if nxt else None, request=self.requests)
                continue
            self.last_answered = i
            return response

    @asynccontextmanager
    async def request_stream(self, *args, **kwargs):
        raise NotImplementedError("the pilot does not stream model responses")
        yield  # pragma: no cover
