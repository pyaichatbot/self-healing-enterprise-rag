# Architecture

## High-Level Flow
1. Request enters API gateway with version and auth checks.
2. Retrieval fetches top-k chunks from indexed corpus.
3. Grading/ranking selects evidence and quality signals.
4. Generation produces draft answer with citations.
5. Guardrails and reflection decide pass/heal flow.
6. Observability emits traces, metrics, and structured events.

## Core Modules
- `shrag.api`: external HTTP contract and control-plane checks
- `shrag.retrieve`/`shrag.grade`: evidence retrieval and ranking
- `shrag.generate`/`shrag.security`: generation and output safety
- `shrag.eval`/`shrag.reflect`/`shrag.heal`: quality feedback loop

## Deployment Topology
- Stateless API replicas behind load balancer
- Managed queue and worker pool for ingestion
- Prometheus/Grafana stack for SLO and incident response
