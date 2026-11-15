#!/usr/bin/env bash
# Resumable: finished files are skipped.
cd /workspace
HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/pod_balthasar/jobs.json --out redraw/pod_balthasar/res_42 --crop --cfg 4 --seed 42 --lora lora/xeno_klein_v4.safetensors
echo RENDER_DONE
