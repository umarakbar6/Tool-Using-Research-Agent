"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: str | Path = ".env") -> None:
    """Load a small .env file without adding another runtime dependency.

    Existing environment variables always win. This intentionally supports the
    common KEY=value form only; it is sufficient for this project.
    """

    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, received {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    model: str = "gpt-5-mini"
    max_steps: int = 8
    max_search_results: int = 5
    fetch_timeout_seconds: int = 12
    max_page_bytes: int = 2_000_000
    max_page_chars: int = 24_000
    max_redirects: int = 3
    max_model_retries: int = 2

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini").strip(),
            max_steps=_positive_int("MAX_STEPS", 8),
            max_search_results=_positive_int("MAX_SEARCH_RESULTS", 5),
            fetch_timeout_seconds=_positive_int("FETCH_TIMEOUT_SECONDS", 12),
            max_page_bytes=_positive_int("MAX_PAGE_BYTES", 2_000_000),
            max_page_chars=_positive_int("MAX_PAGE_CHARS", 24_000),
            max_redirects=_positive_int("MAX_REDIRECTS", 3),
            max_model_retries=_positive_int("MAX_MODEL_RETRIES", 2),
        )
