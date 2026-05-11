from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import jwt


@dataclass(slots=True)
class Identity:
    user_id: str
    tenant_id: str
    roles: tuple[str, ...]


def _decode_token(
    token: str,
    *,
    secret: str,
    algorithm: str,
    jwks_url: str | None,
    issuer: str | None,
    audience: str | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"algorithms": [algorithm]}
    if issuer:
        kwargs["issuer"] = issuer
    if audience:
        kwargs["audience"] = audience

    if jwks_url and algorithm.upper().startswith("RS"):
        jwk_client = jwt.PyJWKClient(jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        return cast(dict[str, Any], jwt.decode(token, signing_key.key, **kwargs))
    return cast(dict[str, Any], jwt.decode(token, secret, **kwargs))


def parse_bearer_token(
    authorization: str | None,
    *,
    secret: str,
    algorithm: str,
    default_tenant_id: str,
    jwks_url: str | None = None,
    issuer: str | None = None,
    audience: str | None = None,
) -> Identity | None:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload: dict[str, Any] = _decode_token(
            token,
            secret=secret,
            algorithm=algorithm,
            jwks_url=jwks_url,
            issuer=issuer,
            audience=audience,
        )
    except Exception:
        return None
    user_id = str(payload.get("sub") or payload.get("user_id") or "anonymous")
    tenant_id = str(payload.get("tenant_id") or default_tenant_id)
    roles_raw = payload.get("roles") or payload.get("role") or ["reader"]
    if isinstance(roles_raw, str):
        roles = tuple(sorted({part.strip() for part in roles_raw.split(",") if part.strip()}))
    else:
        roles = tuple(sorted({str(r).strip() for r in roles_raw if str(r).strip()}))
    return Identity(user_id=user_id, tenant_id=tenant_id, roles=roles or ("reader",))
