from __future__ import annotations


def cutover(active_version: str, candidate_version: str) -> str:
    if not candidate_version:
        return active_version
    return candidate_version
