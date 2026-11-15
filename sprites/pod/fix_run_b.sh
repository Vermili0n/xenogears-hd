#!/usr/bin/env bash
# Pod B, after its production shards are DONE: render a fix job list on the 3 free GPUs (shard i of 3 on GPU i) into
# its own folder. Does not touch res_prod. Resumable (infer_pod skips existing outputs).
#   setsid nohup bash fix_run_b.sh prod/jobs_fixtest_g1.json res_fixtest2 </dev/null >fix_run_b.out 2>&1 &
#   setsid nohup bash fix_run_b.sh prod/jobs_fix.json res_fix3 </dev/null >fix_run_b.out 2>&1 &
# Log per GPU: fix_b_<i>.log; marker FIX <i> DONE.
cd /workspace
JOBS=$1; OUT=$2
for d in prod_1.log prod_2.log prod_3.log; do
  grep -q "PROD .* DONE" "$d" || { echo "production shard not done: $d - refusing to start"; exit 1; }
done
export HF_HOME=/workspace/hf
for i in 0 1 2; do
  (CUDA_VISIBLE_DEVICES=$i python infer_pod.py --jobs "$JOBS" --out "$OUT" --crop --cfg 4 --seed 42 --shard $i/3 \
     --lora lora/xeno_klein_v4.safetensors > fix_b_$i.log 2>&1; echo "FIX $i DONE" >> fix_b_$i.log) &
done
wait
