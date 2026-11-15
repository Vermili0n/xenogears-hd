#!/usr/bin/env bash
# Pilot 5 (28.10): Fei deathblow sets 3413_0..3423_0 (cover frames) + 2988_0:58 (lost in pilot 4).
# One process (one pipeline copy fits 32 GB), cfg 4, 28 steps, seed 42, crop. LoRA = $1 (chosen after test4).
cd /workspace
export HF_HOME=/workspace/hf
LORA=${1:?lora path}
python infer_pod.py --jobs render_pilot5/jobs.json --out res_pilot5 --crop --cfg 4 --seed 42 --lora "$LORA" > pilot5.log 2>&1
echo PILOT5 DONE >> pilot5.log
