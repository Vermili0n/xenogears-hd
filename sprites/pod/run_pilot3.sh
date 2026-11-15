#!/usr/bin/env bash
# Pilot 3 (28.10): Alice + Timothy (story), 2 Lahan villagers (NPC boards), Fei battle set 2709_3.
# One process (one pipeline copy fits 32 GB), cfg 4, 28 steps, seed 42, crop. LoRA = $1 (chosen after test4).
cd /workspace
export HF_HOME=/workspace/hf
LORA=${1:?lora path}
python infer_pod.py --jobs render_pilot3/jobs.json --out res_pilot3 --crop --cfg 4 --seed 42 --lora "$LORA" > pilot3.log 2>&1
echo PILOT3 DONE >> pilot3.log
