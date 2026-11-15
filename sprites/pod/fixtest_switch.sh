#!/usr/bin/env bash
# Pause shard 0 (render pid given explicitly - no pattern matching), run the fix-list hint test, then resume shard 0
# on the deduplicated queue with the full wrapper (v4 rest, v2 gears, PROD 0 DONE).
#   setsid nohup bash fixtest_switch.sh <pid of the shard-0 render> </dev/null >fixtest_switch.out 2>&1 &
cd /workspace
P=$1
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
python infer_pod.py --jobs prod/jobs_fixtest.json --out res_fixtest --crop --cfg 4 --seed 42 \
  --lora lora/xeno_klein_v4.safetensors > fixtest.log 2>&1
echo FIXTEST_DONE >> fixtest.log
bash prod_run_dd.sh 0 4 0
