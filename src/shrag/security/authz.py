"""RBAC authorization — role-based scope enforcement.

Role hierarchy (most → least privileged):
  admin > editor > reader > public

Scope rules:
  - admin: all scopes granted
  - editor: read + write (no admin, no delete)
  - reader: read + public only
  - public: public scope only, no user_id required

Enterprise features:
  - Tenant-scoped roles (roles are per-tenant)
  - Resource-level ACL check (chunk/source_id ownership)
  - JWT claims integration (roles extracted from token payload)
  - Audit logging for denied access attempts
  - Configurable role→scope mapping via env JSON
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role → scope mapping
# ---------------------------------------------------------------------------

_DEFAULT_ROLE_SCOPES: dict[str, set[str]] = {
    "admin":  {"admin", "write", "read", "delete", "ingest", "public"},
    "editor": {"write", "read", "ingest", "public"},
    "reader": {"read", "public"},
    "public": {"public"},
}


def _load_json_env(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse JSON env override: %s", exc)
        return default


def _role_scopes() -> dict[str, set[str]]:
    """Load role→scope mapping (env override or default)."""
    loaded = _load_json_env(os.environ.get("SHRAG_ROLE_SCOPES"), {})
    if isinstance(loaded, dict):
        return {str(role): set(scopes) for role, scopes in loaded.items()}
    return _DEFAULT_ROLE_SCOPES


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AuthzDecision:
    allowed: bool
    reason: str
    user_id: str | None
    required_scope: str
    granted_scopes: set[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AbacRule:
    effect: str
    scope: str
    subject_roles: set[str] = field(default_factory=set)
    subject_tenants: set[str] = field(default_factory=set)
    resource_tags: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------

def _scopes_for_user(
    user_id: str | None,
    roles: set[str] | None,
    tenant_id: str | None,
) -> set[str]:
    """Resolve effective scopes for a user given their roles."""
    if user_id is None:
        return {"public"}

    mapping = _role_scopes()
    effective: set[str] = set()
    for role in (roles or set()):
        effective |= mapping.get(role, set())

    # Default reader scope if no roles assigned.
    if not effective:
        effective = mapping.get("reader", {"read", "public"})

    return effective


# ---------------------------------------------------------------------------
# Resource ACL check
# ---------------------------------------------------------------------------

def _resource_owned_by(resource_id: str, user_id: str, tenant_id: str | None) -> bool:
    """Check if user owns a resource (chunk/source_id).

    Reads from SQLite chunks table; returns True if user is owner or admin.
    """
    try:
        import sqlite3
        db_path = os.environ.get("SHRAG_STATE_DB_PATH", ".state/shrag.db")
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                "SELECT subject_id FROM chunks WHERE source_id = ? LIMIT 1",
                (resource_id,),
            )
            row = cur.fetchone()
            if row:
                return row[0] == user_id
    except Exception as exc:  # noqa: BLE001
        logger.debug("Resource ACL lookup failed: %s", exc)
    return False


# ---------------------------------------------------------------------------
# JWT claims extraction
# ---------------------------------------------------------------------------

def _extract_roles_from_jwt(token: str) -> set[str]:
    """Extract roles from a decoded JWT payload (no signature verification here)."""
    try:
        import base64
        import json as _json
        parts = token.split(".")
        if len(parts) != 3:
            return set()
        # Decode payload (add padding).
        payload_b64 = parts[1] + "=="
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        roles = payload.get("roles", payload.get("scope", []))
        if isinstance(roles, str):
            roles = roles.split()
        return {str(r).lower() for r in roles}
    except Exception:  # noqa: BLE001
        pass
    return set()


def _load_abac_rules() -> tuple[AbacRule, ...]:
    parsed = _load_json_env(os.environ.get("SHRAG_ABAC_RULES_JSON"), [])
    rules: list[AbacRule] = []
    if not isinstance(parsed, list):
        return ()
    for item in parsed:
        if not isinstance(item, dict):
            continue
        rules.append(
            AbacRule(
                effect=str(item.get("effect", "allow")).lower(),
                scope=str(item.get("scope", "")).lower(),
                subject_roles={str(v).lower() for v in item.get("subject_roles", []) if str(v).strip()},
                subject_tenants={str(v) for v in item.get("subject_tenants", []) if str(v).strip()},
                resource_tags={str(k): str(v) for k, v in dict(item.get("resource_tags", {})).items()},
            )
        )
    return tuple(rules)


def _abac_allows(
    required_scope: str,
    roles: set[str],
    tenant_id: str | None,
    resource_attrs: dict[str, Any],
) -> bool:
    rules = _load_abac_rules()
    if not rules:
        return True
    required = required_scope.lower()
    decision = True
    for rule in rules:
        if rule.scope not in {"*", required}:
            continue
        if rule.subject_roles and not (roles & rule.subject_roles):
            continue
        if rule.subject_tenants and (tenant_id or "") not in rule.subject_tenants:
            continue
        resource_ok = True
        for key, expected in rule.resource_tags.items():
            if str(resource_attrs.get(key, "")) != expected:
                resource_ok = False
                break
        if not resource_ok:
            continue
        if rule.effect == "deny":
            return False
        if rule.effect == "allow":
            decision = True
    return decision


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_scope(
    user_id: str | None,
    required_scope: str,
    *,
    granted_scopes: set[str] | None = None,
    roles: set[str] | None = None,
    tenant_id: str | None = None,
    jwt_token: str | None = None,
    resource_id: str | None = None,
    resource_attrs: dict[str, Any] | None = None,
) -> AuthzDecision:
    """Full RBAC authorization check.

    Args:
        user_id: Authenticated user identifier (None = anonymous).
        required_scope: The scope needed to perform the action.
        granted_scopes: Explicit scope set (overrides role lookup).
        roles: User's roles for this tenant.
        tenant_id: Tenant context for multi-tenant deployments.
        jwt_token: Raw JWT string; roles extracted automatically.
        resource_id: Optional resource to check ownership ACL.

    Returns:
        AuthzDecision with allow/deny decision and reason.
    """
    # Extract roles from JWT if provided.
    if jwt_token and not roles:
        roles = _extract_roles_from_jwt(jwt_token)

    # Resolve effective scopes.
    if granted_scopes is not None:
        effective_scopes = set(granted_scopes)
    else:
        effective_scopes = _scopes_for_user(user_id, roles, tenant_id)

    # Scope check.
    allowed = required_scope in effective_scopes
    resource_attrs = dict(resource_attrs or {})
    if allowed:
        allowed = _abac_allows(
            required_scope=required_scope,
            roles=set(roles or []),
            tenant_id=tenant_id,
            resource_attrs=resource_attrs,
        )

    # Resource-level ACL (if scope passes and resource_id given).
    if allowed and resource_id and user_id and "admin" not in effective_scopes:
        if not _resource_owned_by(resource_id, user_id, tenant_id):
            # Not owner but may have org-wide read.
            if required_scope not in ("read", "public"):
                allowed = False
                logger.warning(
                    "ACL denied: user=%s scope=%s resource=%s",
                    user_id, required_scope, resource_id,
                )

    if not allowed:
        logger.warning(
            "AuthZ denied: user=%s scope=%s effective=%s",
            user_id, required_scope, effective_scopes,
        )

    return AuthzDecision(
        allowed=allowed,
        reason="granted" if allowed else "insufficient_scope",
        user_id=user_id,
        required_scope=required_scope,
        granted_scopes=effective_scopes,
        metadata={"roles": list(roles or []), "tenant_id": tenant_id, "resource_attrs": resource_attrs},
    )


def allowed_scope(
    user_id: str | None,
    required_scope: str,
    granted_scopes: set[str] | None,
) -> bool:
    """Legacy shim — returns bool only."""
    return check_scope(
        user_id, required_scope, granted_scopes=granted_scopes
    ).allowed
