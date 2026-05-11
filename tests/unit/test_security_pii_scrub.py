from __future__ import annotations

from shrag.security.pii import detect_pii, redact_pii, scrub_metadata
from shrag.security.pii_scrub import scrub


def test_detect_and_redact_pii_email_and_ssn():
    text = "Contact jane@example.com and use SSN 123-45-6789."
    spans = detect_pii(text)

    labels = {span.label for span in spans}
    assert "EMAIL" in labels
    assert "SSN" in labels

    redacted = redact_pii(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_SSN]" in redacted


def test_scrub_metadata_nested_structures():
    payload = {
        "email": "person@corp.com",
        "notes": ["Call +1 (415) 555-0199", {"ssn": "123-45-6789"}],
    }

    cleaned = scrub_metadata(payload)
    assert "[REDACTED_EMAIL]" in cleaned["email"]
    assert "[REDACTED_PHONE]" in cleaned["notes"][0]
    assert "[REDACTED_SSN]" in cleaned["notes"][1]["ssn"]


def test_pii_scrub_shim_uses_redaction():
    out = scrub("email me at user@example.com")
    assert out == "email me at [REDACTED_EMAIL]"
