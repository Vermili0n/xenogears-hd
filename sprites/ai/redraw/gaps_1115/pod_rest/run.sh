#!/usr/bin/env bash
# Resumable: finished files are skipped. Each job carries its seed (split per seed below).
cd /workspace
HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/pod_rest/jobs_v4_s7.json --out redraw/pod_rest/res_v4_7 --crop --cfg 4 --seed 7 --lora lora/xeno_klein_v4.safetensors
HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/pod_rest/jobs_v4_s11.json --out redraw/pod_rest/res_v4_11 --crop --cfg 4 --seed 11 --lora lora/xeno_klein_v4.safetensors
HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/pod_rest/jobs_v4_s23.json --out redraw/pod_rest/res_v4_23 --crop --cfg 4 --seed 23 --lora lora/xeno_klein_v4.safetensors
HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/pod_rest/jobs_v4_s42.json --out redraw/pod_rest/res_v4_42 --crop --cfg 4 --seed 42 --lora lora/xeno_klein_v4.safetensors
HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/pod_rest/jobs_v2_s42.json --out redraw/pod_rest/res_v2_42 --crop --cfg 4 --seed 42 --lora lora/xeno_klein_v2.safetensors
echo RENDER_DONE
