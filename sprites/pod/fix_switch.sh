#!/usr/bin/env bash
# Pause shard 0 on this pod, render a side job list into its own folder, then resume shard 0 on the deduplicated
# queue with the full wrapper (v4 rest, v2 gears, PROD 0 DONE). PIDs are passed explicitly - never pattern-kill.
#   setsid nohup bash fix_switch.sh "<wrapper pids, space separated>" <render pid> <jobs json> <out dir> \
#     </dev/null >fix_switch.out 2>&1 &
cd /workspace
WRAP=$1; P=$2; JOBS=$3; OUT=$4
[ -n "$WRAP" ] && kill -9 $WRAP
if [ -n "$P" ]; then
  kill "$P"
  for i in $(seq 20); do kill -0 "$P" 2>/dev/null || break; sleep 2; done
fi
python - <<'PY'
import glob, os, time
from PIL import Image
for f in glob.glob('res_prod/*/*.png'):
    if time.time() - os.path.getmtime(f) < 180:
        try:
            with Image.open(f) as im:
                im.load()
        except Exception:
            print('BROKEN removed', f)
            os.remove(f)
print('recent renders checked')
PY
export HF_HOME=/workspace/hf CUDA_VISIBLE_DEVICES=0
python infer_pod.py --jobs "$JOBS" --out "$OUT" --crop --cfg 4 --seed 42 \
  --lora lora/xeno_klein_v4.safetensors > side_job.log 2>&1
echo SIDE_JOB_DONE >> side_job.log
bash prod_run_dd.sh 0 4 0
