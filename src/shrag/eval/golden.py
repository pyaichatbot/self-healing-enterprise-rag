from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GoldenCase:
    case_id: str
    query: str
    expected_substring: str


def pass_golden(answer: str, case: GoldenCase) -> bool:
    return case.expected_substring.lower() in answer.lower()
