#!/usr/bin/env bash
# The seeds one after the other. Resumable: finished files are skipped.
cd /workspace
for s in 7 11 23; do
  HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/zero_block/jobs.json --out redraw/zero_block/res_$s --crop --cfg 4 --seed $s --lora lora/xeno_klein_v4.safetensors
done
echo RENDER_DONE
