from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True, slots=True)
class VersionPolicy:
    current: str
    supported: tuple[str, ...]
    deprecated: tuple[str, ...] = ()


POLICY = VersionPolicy(
    current="2026-05-01",
    supported=("2026-05-01", "2026-04-01"),
    deprecated=("2026-04-01",),
)


def require_api_version(x_api_version: str | None = Header(default=None)) -> str:
    """Validate API version header and enforce deprecation policy."""

    if x_api_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing X-API-Version header; supported={','.join(POLICY.supported)}",
        )
    if x_api_version not in POLICY.supported:
        raise HTTPException(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            detail=f"Unsupported API version {x_api_version}; current={POLICY.current}",
        )
    if x_api_version in POLICY.deprecated:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"API version {x_api_version} is deprecated; use {POLICY.current}",
        )
    return x_api_version
