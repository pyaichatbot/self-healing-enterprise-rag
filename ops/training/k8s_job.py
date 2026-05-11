from __future__ import annotations

from ops.training.job_spec import TrainJobSpec


def render_training_job_yaml(spec: TrainJobSpec) -> str:
    method = spec.method.lower()
    return f"""apiVersion: batch/v1
kind: Job
metadata:
  name: shrag-finetune-{spec.run_id}
  labels:
    app: self-healing-rag
    workload: finetune
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        app: self-healing-rag
        workload: finetune
    spec:
      restartPolicy: Never
      nodeSelector:
        nvidia.com/gpu.product: "{spec.gpu_type}"
      containers:
        - name: trainer
          image: "${{SHRAG_FINETUNE_TRAINER_IMAGE}}"
          imagePullPolicy: IfNotPresent
          env:
            - name: SHRAG_FINETUNE_RUN_ID
              value: "{spec.run_id}"
            - name: SHRAG_FINETUNE_DATASET_ID
              value: "{spec.dataset_id}"
            - name: SHRAG_FINETUNE_DATASET_VERSION
              value: "{spec.dataset_version}"
            - name: SHRAG_FINETUNE_BASE_MODEL
              value: "{spec.base_model}"
            - name: SHRAG_FINETUNE_METHOD
              value: "{method}"
            - name: SHRAG_FINETUNE_OUTPUT_MODEL_ID
              value: "{spec.output_model_id}"
            - name: SHRAG_FINETUNE_OUTPUT_PATH
              value: "{spec.output_path}"
          resources:
            limits:
              nvidia.com/gpu: {spec.gpu_count}
"""
