#!/bin/bash
# waits for the battle_self_fix run, then renders the Grahf frames with three seeds
cd /workspace
(setsid nohup sh -c "while ! grep -q RENDER_DONE redraw/battle_self_fix/infer.log 2>/dev/null; do sleep 15; done; for S in 7 123 2026; do HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/battle_grahf_fix/jobs.json --out redraw/battle_grahf_fix/res_s\$S --crop --cfg 4 --seed \$S --lora lora/xeno_klein_v4.safetensors; done; echo RENDER_DONE" > redraw/battle_grahf_fix/infer.log 2>&1 &)
echo "queued"
