#!/usr/bin/env bash
# Eyepatch by masked repaint of the head close-ups. Resumable.
cd /workspace
export PYTHONPATH=/workspace HF_HOME=/workspace/hf
for s in 7 11 23 31; do
  python repaint_pod.py --jobs redraw/eyepatch3/jobs.json --out redraw/eyepatch3/res_$s --seed $s --lora lora/xeno_klein_v4.safetensors --neg "goggles, visor, sunglasses, mask, both eyes covered, green eyes, brown eyes"
done
echo RENDER_DONE
