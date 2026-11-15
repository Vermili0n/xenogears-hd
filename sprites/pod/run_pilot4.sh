#!/usr/bin/env bash
# Pilot 4 (28.10): Fei battle sets 2988_0 + 3005_0, part-cover frames only (186 frames + heads).
# One process (one pipeline copy fits 32 GB), cfg 4, 28 steps, seed 42, crop. LoRA = $1 (chosen after test4).
cd /workspace
export HF_HOME=/workspace/hf
LORA=${1:?lora path}
python infer_pod.py --jobs render_pilot4/jobs.json --out res_pilot4 --crop --cfg 4 --seed 42 --lora "$LORA" > pilot4.log 2>&1
echo PILOT4 DONE >> pilot4.log
