#!/usr/bin/env bash
cd /workspace
export PYTHONPATH=/workspace HF_HOME=/workspace/hf
for s in 7 11; do for st in 55 68; do
  python repaint_pod.py --jobs redraw/eyepatch4/jobs_r3.json --out redraw/eyepatch4/r3_${s}_$st --seed $s --strength 0.$st --lora lora/xeno_klein_v4.safetensors 2>&1 | grep -v 'it/s' | tail -1
done; done
python repaint_pod.py --jobs redraw/maison2/jobs.json --out redraw/maison2/m_7_60 --seed 7 --strength 0.60 --lora lora/xeno_klein_v4.safetensors 2>&1 | grep -v 'it/s' | tail -1
echo RENDER_DONE
