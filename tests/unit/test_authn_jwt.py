import jwt

from shrag.security.authn import parse_bearer_token


def test_parse_bearer_token_extracts_identity():
    token = jwt.encode(
        {"sub": "alice", "tenant_id": "tenant-a", "roles": ["reader", "writer"]},
        "dev-secret-change-me",
        algorithm="HS256",
    )
    identity = parse_bearer_token(
        f"Bearer {token}",
        secret="dev-secret-change-me",
        algorithm="HS256",
        default_tenant_id="public",
    )
    assert identity is not None
    assert identity.user_id == "alice"
    assert identity.tenant_id == "tenant-a"
    assert "writer" in identity.roles
