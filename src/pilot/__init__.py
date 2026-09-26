"""Autonomous LLM pilot for the game harness.

Runs the verified autopilot for routine turns and hands each blocker to an LLM (any provider
supported by pydantic-ai), which decides using the corpus, acts through the game tools, and
records what it learned into the corpus overlay (`corpora/<game>/learned/`).
"""
