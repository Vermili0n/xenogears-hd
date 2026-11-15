#!/usr/bin/env bash
# Maison without the mustache: new board + hint, one seed. Resumable: finished files are skipped.
cd /workspace
HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/maison/jobs.json --out redraw/maison/res_7 --crop --cfg 4 --seed 7 --lora lora/xeno_klein_v4.safetensors
echo RENDER_DONE
