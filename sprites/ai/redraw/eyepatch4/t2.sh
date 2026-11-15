#!/usr/bin/env bash
cd /workspace
export PYTHONPATH=/workspace HF_HOME=/workspace/hf
for s in 7 11; do for st in 50 62; do
  python repaint_pod.py --jobs redraw/eyepatch4/jobs.json --out redraw/eyepatch4/r2_${s}_$st --seed $s --strength 0.$st --lora lora/xeno_klein_v4.safetensors 2>&1 | grep -v 'it/s' | tail -1
done; done
echo T_DONE
