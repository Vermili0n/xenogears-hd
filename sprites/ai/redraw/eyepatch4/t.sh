#!/usr/bin/env bash
cd /workspace
export PYTHONPATH=/workspace HF_HOME=/workspace/hf
for st in 55 70 85; do
  python repaint_pod.py --jobs redraw/eyepatch4/jobs.json --out redraw/eyepatch4/t7_$st --seed 7 --strength 0.$st --lora lora/xeno_klein_v4.safetensors 2>&1 | grep -v 'it/s' | tail -1
done
echo T_DONE
