"""Model health on Now and in Activity (docs/design/2026-10-02-model-guard-design.md, rulings 22-23)."""

from __future__ import annotations

import pytest
from uikit import CONTEXTS, open_context, show

pytestmark = pytest.mark.ui


@pytest.mark.parametrize("scenario", ["deciding"])
@pytest.mark.parametrize("name", list(CONTEXTS))
def test_the_model_health_line_names_skipped_and_cautioned_models(browser, live_servers, name):
    w = open_context(browser, name, live_servers)
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    w.page.wait_for_selector("#model-health:not([hidden])", timeout=15000)
    line = w.page.text_content("#model-health")
    assert "Skipped: Gemini 3.8 Flash until" in line and "(overloaded (503), 3rd time)" in line
    assert "Gemini 3.7 Flash after other families" in line
    assert "warn" in w.page.get_attribute("#model-health", "class")
    assert w.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no sideways scroll"
    w.context.close()


@pytest.mark.parametrize("scenario", ["deciding"])
def test_activity_says_what_the_guard_did(browser, live_servers):
    w = open_context(browser, "desktop-light", live_servers)
    w.page.goto(w.base + "/", wait_until="domcontentloaded")
    show(w.page, "activity")
    w.page.wait_for_selector("#feed li")
    text = w.page.text_content("#feed")
    assert "Gemini 3.8 Flash skipped until" in text and "3rd time" in text
    assert "No model could answer (chat): Gemini 3.8 Flash overloaded (503)" in text
    assert "no other model was left" in text and "used the model" not in text
    w.context.close()


@pytest.mark.parametrize("scenario", ["deciding"])
def test_only_open_and_broken_breakers_are_problems(browser, live_servers):
    """A trial, a model that answers again and a cleared broken mark are under Model, not Problems."""
    w = open_context(browser, "desktop-light", live_servers)
    page = w.page
    page.goto(w.base + "/", wait_until="domcontentloaded")
    show(page, "activity")
    page.wait_for_selector("#feed li")
    calm = ("Sonnet 5 (API) may be tried again", "Trying Gemini 3.1 Pro again", "Gemini 3.1 Pro answers again")
    text = page.text_content("#feed")
    assert all(s in text for s in calm), text
    assert "Sonnet 5 (API) answers again" not in text, "a cleared mark is not an answer"
    page.click('#feed-filters [data-filter="problems"]')
    problems = page.text_content("#feed")
    assert "Gemini 3.8 Flash skipped until" in problems and "Sonnet 5 (API) cannot be used (unusable (404))" in problems
    assert not any(s in problems for s in calm), problems
    page.click('#feed-filters [data-filter="model"]')
    model = page.text_content("#feed")
    assert all(s in model for s in calm) and "Gemini 3.8 Flash skipped until" in model
    w.context.close()
