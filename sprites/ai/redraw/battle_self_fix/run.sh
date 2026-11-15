#!/bin/bash
cd /workspace
if pgrep -f "[i]nfer_pod.py --jobs redraw/battle_self_fix/jobs.json" >/dev/null; then echo "already running"; exit 0; fi
(setsid nohup sh -c "for S in 7 123 2026; do HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/battle_self_fix/jobs.json --out redraw/battle_self_fix/res_s\$S --crop --cfg 4 --seed \$S --lora lora/xeno_klein_v4.safetensors; done; echo RENDER_DONE" > redraw/battle_self_fix/infer.log 2>&1 &)
echo "started, the window can be closed"
