# Fine-Tuning Readiness Gate (H100 Use Case)

This repository now enforces a machine-checkable readiness gate for the fine-tuning lane used in enterprise H100 proposals.

## Reports Required

The gate validates these reports in `.state/`:

- `finetune-dataset-report.json`
- `finetune-training-report.json`
- `finetune-promotion-report.json`

It writes:

- `finetune-readiness-report.json`

## Commands

- Generate simulated evidence:
  - `make finetune-readiness-simulated`
- Generate each simulated stage independently:
  - `make finetune-dataset-simulated`
  - `make finetune-train-simulated`
  - `make finetune-render-job`
  - `make finetune-promote-simulated`
- Validate gate:
  - `make finetune-readiness`
- Validate production-only gate (rejects simulated artifacts):
  - `make finetune-readiness-production-check`
- Enforce in strict release lane:
  - `make release-gate-strict`

## Validation Rules

- Dataset:
  - non-empty `dataset_id` and `dataset_version`
  - `record_count > 0`
  - `pii_scrubbed = true`
  - `license_policy_passed = true`
  - at least one source system listed
- Training:
  - non-empty `run_id` and `base_model`
  - `gpu_count > 0`
  - method in `lora|qlora|sft`
  - `eval_passed = true`
  - training framework in `peft|trl|deepspeed|accelerate`
  - GPU type must be `H100` unless explicitly overridden
- Promotion:
  - candidate model id present
  - explicit approval present
  - approver identity present
  - change ticket present
  - rollback plan reference present

## Env-Driven Release Enforcement

- `SHRAG_RELEASE_REQUIRE_FINETUNE_REPORT=true` enforces fine-tuning readiness report in `release-gate`.
- `release-gate-strict` enforces this requirement by default.
- In strict mode, release gate also requires that fine-tuning readiness was executed with `--require-non-simulated`.

## H100 Runtime Deployment Knobs

Helm values support GPU placement controls:

- `gpu.enabled=true`
- `gpu.productLabelKey=nvidia.com/gpu.product`
- `gpu.productLabelValue=NVIDIA-H100`
- `gpu.runtimeClassName` (optional)
- `nodeSelector`, `tolerations`, `affinity`

## Provenance Mode

- `SHRAG_FINETUNE_PROVENANCE_MODE=simulated` (default) for local dry-runs.
- `SHRAG_FINETUNE_PROVENANCE_MODE=production` for production-evidence lane.
- `release-gate-strict` requires a fine-tuning readiness report generated with non-simulated enforcement.

## Model Registry Backend

Training/promotion supports env-driven model registry backends:

- `SHRAG_MODEL_REGISTRY_BACKEND=local_json` (default)
- `SHRAG_MODEL_REGISTRY_BACKEND=http` with `SHRAG_MODEL_REGISTRY_HTTP_URL=<base-url>`

## Production Execution Evidence

Strict release gate also requires:

- `.state/finetune-training-job.yaml`
- `.state/finetune-training-exec.json`
- `connector-evidence-report-strict.json` with `evidence_mode=live`

These are produced by:

- `make finetune-train`
- `make finetune-render-job`
