#!/usr/bin/env bash
cd /workspace
export PYTHONPATH=/workspace HF_HOME=/workspace/hf
for s in 7 11 23; do
  python repaint_pod.py --jobs redraw/eyepatch3/jobs_t3b.json --out redraw/eyepatch3/t3_$s --seed $s --lora lora/xeno_klein_v4.safetensors --neg "face, eyes, nose, mouth, goggles, visor" 2>&1 | grep -v "it/s" | tail -1
  python repaint_pod.py --jobs redraw/eyepatch3/jobs_t3p.json --out redraw/eyepatch3/t3_$s --seed $s --lora lora/xeno_klein_v4.safetensors --neg "goggles, visor, sunglasses, mask, both eyes covered, green eyes, brown eyes" 2>&1 | grep -v "it/s" | tail -1
done
echo T3_DONE
