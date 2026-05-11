from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RequestContext
from shrag.settings import Settings


def should_sample(context: RequestContext, sample_rate: float = 0.2) -> bool:
    bucket = sum(ord(char) for char in context.request_id) % 100
    return bucket < int(sample_rate * 100)


def sample_requests(requests: Sequence[RequestContext], sample_rate: float = 0.2) -> tuple[RequestContext, ...]:
    return tuple(req for req in requests if should_sample(req, sample_rate=sample_rate))


def canary_window_sample_rate() -> float:
    return float(Settings().eval_canary_sample_rate)


def judge_window_sample_rate() -> float:
    return float(Settings().eval_judge_sample_rate)
