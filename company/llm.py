"""Claude integration for every agent in the company.

A single thin wrapper around the Anthropic SDK. Each agent calls `generate` for
prose or `generate_json` for a structured decision. When no API key is present
(or the SDK call fails), these return ``None`` and the caller falls back to its
deterministic simulation path — so the company always runs.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .config import Settings

log = logging.getLogger("company.llm")


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Any = None
        if settings.simulate:
            log.info("LLM running in SIMULATION mode (no API key or forced).")
            return
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.api_key)
            log.info("LLM using Claude model %s", settings.model)
        except Exception as exc:  # pragma: no cover - import/credential issues
            log.warning("Could not initialize Anthropic client (%s); simulating.", exc)
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def generate(
        self, system: str, user: str, max_tokens: int = 4000,
        model: str | None = None, effort: str | None = None,
    ) -> str | None:
        """Return Claude's text response, or ``None`` to signal "simulate instead"."""
        if not self.available:
            return None
        try:
            resp = self._client.messages.create(
                model=model or self.settings.model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": effort or self.settings.effort},
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if resp.stop_reason == "refusal":
                log.warning("Claude refused a request; falling back to simulation.")
                return None
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception as exc:  # pragma: no cover - network/runtime
            log.warning("Claude call failed (%s); falling back to simulation.", exc)
            return None

    def generate_json(
        self, system: str, user: str, schema: dict, max_tokens: int = 4000,
        model: str | None = None, effort: str | None = None,
    ) -> dict | None:
        """Return a schema-validated dict from Claude, or ``None`` to simulate."""
        if not self.available:
            return None
        try:
            resp = self._client.messages.create(
                model=model or self.settings.model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": effort or self.settings.effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            if resp.stop_reason == "refusal":
                log.warning("Claude refused a structured request; simulating.")
                return None
            text = next((b.text for b in resp.content if b.type == "text"), "")
            return json.loads(text)
        except Exception as exc:  # pragma: no cover - network/runtime
            log.warning("Claude JSON call failed (%s); falling back to simulation.", exc)
            return None
