#!/bin/bash
cd /workspace
if pgrep -f "[i]nfer_pod.py --jobs redraw/battle_rest/jobs.json" >/dev/null; then echo "already running"; exit 0; fi
(setsid nohup sh -c "HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/battle_rest/jobs.json --out redraw/battle_rest/res --crop --cfg 4 --seed 42 --lora lora/xeno_klein_v4.safetensors; echo RENDER_DONE" > redraw/battle_rest/infer.log 2>&1 &)
echo "started, the window can be closed"
