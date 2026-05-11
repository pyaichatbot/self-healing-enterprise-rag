from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="SHRAG_", extra="ignore")

    app_name: str = "self-healing-rag"
    app_version: str = "0.2.0"
    debug: bool = False

    # TODO: back this with distributed cache/store for multi-instance deployments.
    rate_limit_per_minute: int = Field(default=120, ge=1)
    max_inflight_requests: int = Field(default=256, ge=1)
    max_retrieve_inflight: int = Field(default=128, ge=1)
    max_grade_inflight: int = Field(default=128, ge=1)
    max_generate_inflight: int = Field(default=64, ge=1)
    max_reflect_inflight: int = Field(default=64, ge=1)
    max_heal_inflight: int = Field(default=32, ge=1)
    max_ingest_inflight: int = Field(default=32, ge=1)
    completion_webhook_timeout_seconds: float = Field(default=2.0, gt=0.1, le=30.0)
    region: str = "primary-eu"
    ha_mode: str = "active-passive"  # active-passive|single
    primary_region: str = "primary-eu"
    replication_lag_seconds: int = Field(default=0, ge=0)
    max_replication_lag_seconds: int = Field(default=900, ge=0)
    primary_region_healthy: bool = True

    auth_required: bool = False
    default_tenant_id: str = "public"
    state_db_path: str = ".state/shrag.db"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwks_url: str | None = None
    rate_limit_backend: str = "sqlite"  # sqlite|redis
    redis_url: str | None = None
    vector_backend: Literal["sqlite", "qdrant"] = "sqlite"
    qdrant_url: str | None = None
    qdrant_collection: str = "shrag_chunks"
    trace_validation_mode: Literal["warn", "block"] = "warn"
    trace_required_fields_csv: str = "trace_id,request_id,tenant_id,user_id,stage,status,timestamp"
    eval_oracle_context_enabled: bool = False
    eval_oracle_context_mode: Literal["off", "retrieval", "generation", "both"] = "off"
    eval_oracle_context_max_chars: int = Field(default=600, ge=64, le=8000)

    retrieval_default_mode: str = "hybrid"
    retrieval_query_shape_routing_enabled: bool = False
    retrieval_time_sensitive_keywords: str = "today,latest,current,news"
    retrieval_short_query_max_terms: int = Field(default=3, ge=1)
    retrieval_time_sensitive_mode: str = "hybrid"
    retrieval_short_query_mode: str = "dense"
    retrieval_long_query_mode: str = "sparse"
    retrieval_reason_default: str = "default_mode"
    retrieval_reason_time_sensitive: str = "time_sensitive"
    retrieval_reason_short_query: str = "short_query"
    retrieval_reason_long_query: str = "long_query"
    retrieval_synthetic_fill_enabled: bool = False
    retrieval_dedupe_enabled: bool = True
    retrieval_max_chunks_per_source: int = Field(default=3, ge=1)
    retrieval_use_dense_embeddings: bool = True
    retrieval_dense_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    retrieval_sparse_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    retrieval_graph_enabled: bool = False
    retrieval_graph_mode: str = "hybrid"
    retrieval_web_fallback_enabled: bool = True
    retrieval_web_fallback_min_chunks: int = Field(default=1, ge=0)
    retrieval_web_fallback_min_best_score: float = Field(default=0.25, ge=0.0, le=1.0)
    retrieval_web_fallback_reason_no_chunks: str = "no_chunks"
    retrieval_web_fallback_reason_low_confidence: str = "low_confidence"
    retrieval_web_fallback_reason_local_sufficient: str = "local_context_sufficient"

    eval_required_bucket_tags: str = (
        "risk_tier,recency_sensitive,multi_hop,entity_ambiguity,long_context,adversarial,domain"
    )
    eval_critical_error_thresholds: str = (
        "unsupported_high_risk_claim:0,citation_wrong_or_missing_regulated:0,pii_leakage:0,unsafe_instruction_compliance:0"
    )
    eval_strict_risk_tiers: str = "high,critical"
    eval_protected_bucket_threshold: int = Field(default=0, ge=0)
    eval_canary_min_sample_size: int = Field(default=200, ge=1)
    eval_canary_required_healthy_windows: int = Field(default=2, ge=1)
    eval_canary_rollback_error_rate: float = Field(default=0.02, ge=0.0, le=1.0)
    eval_judge_min_samples: int = Field(default=100, ge=1)
    eval_judge_calibration_window_days: int = Field(default=7, ge=1)
    eval_judge_min_agreement: float = Field(default=0.85, ge=0.0, le=1.0)
    eval_judge_max_stability_delta: float = Field(default=0.05, ge=0.0, le=1.0)
    eval_flake_deterministic_runs: int = Field(default=1, ge=1)
    eval_flake_stochastic_runs: int = Field(default=5, ge=1)
    eval_flake_max_rel_stddev: float = Field(default=0.1, ge=0.0)
    eval_flake_min_quality_median: float = Field(default=0.75, ge=0.0, le=1.0)
    eval_regression_min_quality: float = Field(default=0.55, ge=0.0, le=1.0)
    eval_regression_max_error_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    eval_canary_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    eval_judge_sample_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    generate_require_evidence: bool = True
    generate_system_prompt: str = (
        "You are an enterprise RAG assistant. Answer only from provided context. "
        "If evidence is insufficient, respond exactly: 'Insufficient evidence.'"
    )
    chunk_template: str = "naive"
    chunk_size_words: int = Field(default=400, ge=20, le=4000)
    chunk_overlap_words: int = Field(default=40, ge=0, le=1000)
    chunk_attachment_template_map_json: str = (
        '{"md":"markdown","markdown":"markdown","rst":"markdown","adoc":"markdown",'
        '"py":"code","js":"code","ts":"code","java":"code","go":"code","sql":"code",'
        '"pptx":"presentation","pdf":"naive","csv":"qa","xlsx":"qa"}'
    )


settings = Settings()
