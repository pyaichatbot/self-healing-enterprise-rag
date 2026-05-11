from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import os
import urllib.error
import urllib.parse
import urllib.request


@dataclass(slots=True)
class ModelRecord:
    model_id: str
    run_id: str
    base_model: str
    method: str
    dataset_id: str
    dataset_version: str
    status: str
    artifact_path: str
    approved: bool
    approver: str
    change_ticket: str
    rollback_plan_ref: str


def _load_registry(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")))


def _save_registry(path: Path, payload: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def upsert_model_record(path: Path, record: ModelRecord) -> None:
    rows = _load_registry(path)
    as_row = asdict(record)
    replaced = False
    for idx, row in enumerate(rows):
        if str(row.get("model_id", "")) == record.model_id:
            rows[idx] = as_row
            replaced = True
            break
    if not replaced:
        rows.append(as_row)
    _save_registry(path, rows)


def get_model_record(path: Path, model_id: str) -> ModelRecord | None:
    rows = _load_registry(path)
    for row in rows:
        if str(row.get("model_id", "")) == model_id:
            return ModelRecord(
                model_id=str(row.get("model_id", "")),
                run_id=str(row.get("run_id", "")),
                base_model=str(row.get("base_model", "")),
                method=str(row.get("method", "")),
                dataset_id=str(row.get("dataset_id", "")),
                dataset_version=str(row.get("dataset_version", "")),
                status=str(row.get("status", "")),
                artifact_path=str(row.get("artifact_path", "")),
                approved=bool(row.get("approved") is True),
                approver=str(row.get("approver", "")),
                change_ticket=str(row.get("change_ticket", "")),
                rollback_plan_ref=str(row.get("rollback_plan_ref", "")),
            )
    return None


def _registry_backend() -> str:
    return os.environ.get("SHRAG_MODEL_REGISTRY_BACKEND", "local_json").strip().lower()


def _registry_http_base_url() -> str:
    return os.environ.get("SHRAG_MODEL_REGISTRY_HTTP_URL", "").strip()


def _http_get_record(base_url: str, model_id: str) -> dict[str, Any] | None:
    encoded = urllib.parse.quote(model_id, safe="")
    req = urllib.request.Request(f"{base_url.rstrip('/')}/models/{encoded}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload, dict):
                return payload
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return None


def _http_upsert_record(base_url: str, record: ModelRecord) -> None:
    payload = json.dumps(asdict(record)).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/models",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=15):
        return


def get_model_record_backend(path: Path, model_id: str) -> ModelRecord | None:
    backend = _registry_backend()
    if backend == "local_json":
        return get_model_record(path, model_id)
    if backend == "http":
        base_url = _registry_http_base_url()
        if not base_url:
            raise ValueError("missing_env:SHRAG_MODEL_REGISTRY_HTTP_URL")
        row = _http_get_record(base_url, model_id)
        if row is None:
            return None
        return ModelRecord(
            model_id=str(row.get("model_id", "")),
            run_id=str(row.get("run_id", "")),
            base_model=str(row.get("base_model", "")),
            method=str(row.get("method", "")),
            dataset_id=str(row.get("dataset_id", "")),
            dataset_version=str(row.get("dataset_version", "")),
            status=str(row.get("status", "")),
            artifact_path=str(row.get("artifact_path", "")),
            approved=bool(row.get("approved") is True),
            approver=str(row.get("approver", "")),
            change_ticket=str(row.get("change_ticket", "")),
            rollback_plan_ref=str(row.get("rollback_plan_ref", "")),
        )
    raise ValueError(f"unsupported_registry_backend:{backend}")


def upsert_model_record_backend(path: Path, record: ModelRecord) -> None:
    backend = _registry_backend()
    if backend == "local_json":
        upsert_model_record(path, record)
        return
    if backend == "http":
        base_url = _registry_http_base_url()
        if not base_url:
            raise ValueError("missing_env:SHRAG_MODEL_REGISTRY_HTTP_URL")
        _http_upsert_record(base_url, record)
        return
    raise ValueError(f"unsupported_registry_backend:{backend}")
