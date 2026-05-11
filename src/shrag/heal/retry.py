from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import random
from time import sleep
from typing import Callable, TypeVar

import yaml  # type: ignore[import-untyped]

T = TypeVar("T")


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int = 2
    backoff_seconds: float = 0.2
    jitter: bool = True


def load_retry_policy(path: str | None = None) -> RetryPolicy:
    policy_path = path or str(Path(__file__).with_name("retry_policy.yaml"))
    with open(policy_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return RetryPolicy(
        max_attempts=int(raw.get("max_attempts", 2)),
        backoff_seconds=float(raw.get("backoff_seconds", 0.2)),
        jitter=bool(raw.get("jitter", True)),
    )


def run_with_retry(fn: Callable[[], T], policy: RetryPolicy | None = None) -> T:
    cfg = policy or load_retry_policy()
    last_error: Exception | None = None
    for attempt in range(1, cfg.max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover - guarded by tests
            last_error = exc
            if attempt >= cfg.max_attempts:
                break
            delay = cfg.backoff_seconds * attempt
            if cfg.jitter:
                delay += random() * cfg.backoff_seconds
            sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry loop failed without capturing an exception")


def retry_budget(attempt: int, max_attempts: int = 2) -> bool:
    return attempt < max_attempts
