"""Central configuration for the autonomous software company.

Reads from environment variables (and an optional .env file) so the same code
runs on real Claude or in deterministic simulation mode without changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader so we don't add a dependency for one feature."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # Real environment variables win over the .env file.
        os.environ.setdefault(key, value)


_load_dotenv()


# Approximate USD pricing per 1M tokens (input, output) by model, for the
# cost ledger. Used to estimate spend; exact billing comes from the API.
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_PRICE = (5.0, 25.0)


def cost_for(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICING.get(model, _DEFAULT_PRICE)
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str
    effort: str
    db_path: str
    force_simulate: bool
    budget: float

    @property
    def simulate(self) -> bool:
        """True when there is no usable Claude client and we run on canned logic."""
        return self.force_simulate or not self.api_key


def load_settings() -> Settings:
    return Settings(
        api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model=os.environ.get("COMPANY_MODEL", "claude-opus-4-8"),
        effort=os.environ.get("COMPANY_EFFORT", "high"),
        db_path=os.environ.get("COMPANY_DB", str(ROOT / "company.db")),
        force_simulate=os.environ.get("COMPANY_SIMULATE", "0") == "1",
        budget=float(os.environ.get("COMPANY_BUDGET", "25") or 25),
    )


SETTINGS = load_settings()
