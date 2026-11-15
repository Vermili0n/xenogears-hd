#!/usr/bin/env bash
# Eyepatch, second try: own hint per pose, 4 seeds. Resumable.
cd /workspace
for s in 7 11 23 31; do
  HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/eyepatch2/jobs.json --out redraw/eyepatch2/res_$s --crop --cfg 4 --seed $s --lora lora/xeno_klein_v4.safetensors
done
echo RENDER_DONE
