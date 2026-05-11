from __future__ import annotations

import base64
import json

from shrag.security.authz import check_scope


def _jwt_with_roles(roles: list[str]) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"roles": roles}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def test_abac_rule_can_deny_scope(monkeypatch):
    monkeypatch.setenv("SHRAG_ROLE_SCOPES", '{"editor":["write","read","public"]}')
    monkeypatch.setenv(
        "SHRAG_ABAC_RULES_JSON",
        '[{"effect":"deny","scope":"write","subject_roles":["editor"],"resource_tags":{"classification":"restricted"}}]',
    )

    denied = check_scope(
        user_id="u1",
        required_scope="write",
        roles={"editor"},
        tenant_id="t1",
        resource_attrs={"classification": "restricted"},
    )
    assert denied.allowed is False

    allowed = check_scope(
        user_id="u1",
        required_scope="write",
        roles={"editor"},
        tenant_id="t1",
        resource_attrs={"classification": "internal"},
    )
    assert allowed.allowed is True


def test_authz_json_env_parse_fallback(monkeypatch):
    monkeypatch.setenv("SHRAG_ROLE_SCOPES", "{bad-json")
    allowed = check_scope(user_id="u1", required_scope="read", roles={"reader"})
    assert allowed.allowed is True


def test_authz_uses_jwt_roles_when_roles_not_passed(monkeypatch):
    monkeypatch.setenv("SHRAG_ROLE_SCOPES", '{"editor":["write","read","public"]}')
    token = _jwt_with_roles(["editor"])
    decision = check_scope(user_id="u1", required_scope="write", jwt_token=token)
    assert decision.allowed is True


def test_authz_public_anonymous_scope_only():
    assert check_scope(user_id=None, required_scope="public").allowed is True
    assert check_scope(user_id=None, required_scope="read").allowed is False


def test_authz_acl_denies_non_owner_for_write(monkeypatch):
    monkeypatch.setattr("shrag.security.authz._resource_owned_by", lambda resource_id, user_id, tenant_id: False)
    decision = check_scope(
        user_id="u1",
        required_scope="write",
        roles={"editor"},
        resource_id="r1",
    )
    assert decision.allowed is False


def test_authz_acl_allows_read_even_if_not_owner(monkeypatch):
    monkeypatch.setattr("shrag.security.authz._resource_owned_by", lambda resource_id, user_id, tenant_id: False)
    decision = check_scope(
        user_id="u1",
        required_scope="read",
        roles={"reader"},
        resource_id="r1",
    )
    assert decision.allowed is True
