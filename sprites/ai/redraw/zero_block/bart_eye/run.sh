#!/usr/bin/env bash
# Every seed at every strength. Resumable: finished files are skipped.
cd /workspace
for s in 7 11 23 31; do
  HF_HOME=/workspace/hf python repaint_pod.py --jobs redraw/zero_block/bart_eye/jobs.json --out redraw/zero_block/bart_eye/res_055_$s --seed $s --strength 0.55 --lora lora/xeno_klein_v4.safetensors
done
for s in 7 11 23 31; do
  HF_HOME=/workspace/hf python repaint_pod.py --jobs redraw/zero_block/bart_eye/jobs.json --out redraw/zero_block/bart_eye/res_068_$s --seed $s --strength 0.68 --lora lora/xeno_klein_v4.safetensors
done
echo RENDER_DONE
