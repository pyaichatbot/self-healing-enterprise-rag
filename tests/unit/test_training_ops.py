from __future__ import annotations

import json
from pathlib import Path

from ops.training.job_spec import build_train_job_spec, to_payload
from ops.training.k8s_job import render_training_job_yaml
from ops.training.model_registry import (
    ModelRecord,
    get_model_record,
    get_model_record_backend,
    upsert_model_record,
    upsert_model_record_backend,
)
from ops.verification.finetune_readiness import run_finetune_gate


def test_build_train_job_spec_uses_env_defaults(monkeypatch):
    monkeypatch.setenv("SHRAG_FINETUNE_BASE_MODEL", "m-base")
    monkeypatch.setenv("SHRAG_FINETUNE_METHOD", "lora")
    monkeypatch.setenv("SHRAG_FINETUNE_GPU_TYPE", "H100")
    monkeypatch.setenv("SHRAG_FINETUNE_GPU_COUNT", "8")
    spec = build_train_job_spec(
        run_id="r1",
        dataset_id="d1",
        dataset_version="v1",
        output_model_id="m1",
    )
    payload = to_payload(spec)
    assert payload["base_model"] == "m-base"
    assert payload["method"] == "lora"
    assert payload["gpu_count"] == 8


def test_model_registry_upsert_and_get(tmp_path):
    path = tmp_path / "model-registry.json"
    upsert_model_record(
        path,
        ModelRecord(
            model_id="m1",
            run_id="r1",
            base_model="b",
            method="qlora",
            dataset_id="d",
            dataset_version="v",
            status="trained",
            artifact_path="/tmp/m1",
            approved=False,
            approver="",
            change_ticket="",
            rollback_plan_ref="",
        ),
    )
    rec = get_model_record(path, "m1")
    assert rec is not None
    assert rec.model_id == "m1"


def test_model_registry_http_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("SHRAG_MODEL_REGISTRY_BACKEND", "http")
    monkeypatch.setenv("SHRAG_MODEL_REGISTRY_HTTP_URL", "https://registry.example")
    seen = {}

    def _fake_put(base_url, record):  # type: ignore[no-untyped-def]
        seen["put"] = (base_url, record.model_id)

    def _fake_get(base_url, model_id):  # type: ignore[no-untyped-def]
        seen["get"] = (base_url, model_id)
        return {
            "model_id": model_id,
            "run_id": "r1",
            "base_model": "b",
            "method": "qlora",
            "dataset_id": "d",
            "dataset_version": "v",
            "status": "trained",
            "artifact_path": "/tmp/m1",
            "approved": False,
            "approver": "",
            "change_ticket": "",
            "rollback_plan_ref": "",
        }

    monkeypatch.setattr("ops.training.model_registry._http_upsert_record", _fake_put)
    monkeypatch.setattr("ops.training.model_registry._http_get_record", _fake_get)
    record = ModelRecord("m1", "r1", "b", "qlora", "d", "v", "trained", "/tmp/m1", False, "", "", "")
    upsert_model_record_backend(tmp_path / "ignored.json", record)
    out = get_model_record_backend(tmp_path / "ignored.json", "m1")
    assert out is not None and out.model_id == "m1"
    assert seen["put"] == ("https://registry.example", "m1")
    assert seen["get"] == ("https://registry.example", "m1")


def test_model_registry_http_backend_requires_url(monkeypatch, tmp_path):
    monkeypatch.setenv("SHRAG_MODEL_REGISTRY_BACKEND", "http")
    monkeypatch.delenv("SHRAG_MODEL_REGISTRY_HTTP_URL", raising=False)
    record = ModelRecord("m1", "r1", "b", "qlora", "d", "v", "trained", "/tmp/m1", False, "", "", "")
    try:
        upsert_model_record_backend(tmp_path / "ignored.json", record)
    except ValueError as exc:
        assert "SHRAG_MODEL_REGISTRY_HTTP_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected missing HTTP URL error")


def test_simulated_training_and_promotion_commands(tmp_path):
    state_dir = tmp_path / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)

    from ops.training.run_dataset_prep_simulated import main as dataset_main
    from ops.training.run_training_simulated import main as train_main
    from ops.training.run_promotion import main as promote_main

    import sys

    argv_orig = list(sys.argv)
    try:
        sys.argv = ["run_dataset_prep_simulated.py", "--state-dir", str(state_dir)]
        assert dataset_main() == 0
        sys.argv = ["run_training_simulated.py", "--state-dir", str(state_dir)]
        assert train_main() == 0
        sys.argv = [
            "run_promotion.py",
            "--state-dir",
            str(state_dir),
            "--model-id",
            "eng-assistant-v1",
            "--approver",
            "board",
            "--change-ticket",
            "CHG-1",
            "--rollback-plan-ref",
            "rb-1",
        ]
        assert promote_main() == 0
    finally:
        sys.argv = argv_orig

    assert (state_dir / "finetune-dataset-report.json").exists()
    assert (state_dir / "finetune-training-report.json").exists()
    assert (state_dir / "finetune-promotion-report.json").exists()
    registry = json.loads((state_dir / "model-registry.json").read_text(encoding="utf-8"))
    assert any(row["status"] == "promoted" for row in registry)

    ok, failures, _ = run_finetune_gate(state_dir=Path(state_dir))
    assert ok is True
    assert failures == []


def test_render_k8s_job_yaml_contains_h100_and_gpu_count():
    spec = build_train_job_spec(
        run_id="r1",
        dataset_id="d1",
        dataset_version="v1",
        output_model_id="m1",
        gpu_type="H100",
        gpu_count=4,
    )
    rendered = render_training_job_yaml(spec)
    assert "kind: Job" in rendered
    assert "nvidia.com/gpu.product" in rendered
    assert "H100" in rendered
    assert "nvidia.com/gpu: 4" in rendered
