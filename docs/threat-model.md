# Threat Model

## Assets
- User prompts and conversation history.
- Retrieved documents and embeddings.
- Model responses and telemetry.
- API keys, tokens, and service credentials.

## Trust Boundaries
- External clients -> API gateway.
- API service -> retrieval/index stores.
- API service -> model provider(s).
- Observability stack receiving operational telemetry.

## Key Threats
- Prompt injection and retrieval poisoning.
- Data exfiltration from logs or model output.
- Credential compromise in CI/CD or runtime.
- Denial of service against retrieval and generation paths.

## Mitigations
- Input validation and policy-enforced tool access.
- Retrieval source validation and signed content pipeline.
- Secret rotation and workload identity.
- Rate limiting, circuit breakers, and graceful degradation.

## Residual Risk
- Third-party model behavior drift.
- Zero-day dependencies.
- Governance gaps in newly onboarded data sources.
