#!/usr/bin/env bash
# Pod B, 29.10 evening, after its production shards (and shard 0's tail, tail_run_b.sh) are done:
#   1) hint test        prod/jobs_fixtest2.json  -> res_fixtest2   (54 jobs: plain vs hint per kind, 2 whole-group samples)
#   2) whole groups     prod/jobs_rebrd_8c2f0a.json (Krelian past board) + prod/jobs_rehint_f4eb00.json (Ramsus white)
#                       -> res_regroup
#   3) fix list         prod/jobs_fix.json -> res_fix3
# each on the 3 GPUs (shard i/3 on GPU i), markers in fix_evening.log: "STEP <n> DONE". Resumable: rerun skips outputs.
# Steps can be limited:  bash fix_evening_b.sh 1     (only the test)   bash fix_evening_b.sh 2 3
#   setsid nohup bash fix_evening_b.sh 1 2 3 </dev/null >fix_evening.out 2>&1 &
cd /workspace
[ "$(cat rebal_state 2>/dev/null)" = running ] && { echo "shard 0 tail still running - refusing"; exit 1; }
for d in prod_1.log prod_2.log prod_3.log; do
  grep -q "PROD .* DONE" "$d" || { echo "production shard not done: $d - refusing to start"; exit 1; }
done
export HF_HOME=/workspace/hf
run3() {  # <jobs json> <out dir> <tag>
  for i in 0 1 2; do
    CUDA_VISIBLE_DEVICES=$i python infer_pod.py --jobs "$1" --out "$2" --crop --cfg 4 --seed 42 --shard $i/3 \
      --lora lora/xeno_klein_v4.safetensors > "fix_$3_$i.log" 2>&1 &
  done
  wait
}
STEPS=${*:-1 2 3}
for s in $STEPS; do
  case $s in
    1) run3 prod/jobs_fixtest2.json res_fixtest2 test ;;
    2) run3 prod/jobs_rebrd_8c2f0a.json res_regroup krel; run3 prod/jobs_rehint_f4eb00.json res_regroup rams ;;
    3) run3 prod/jobs_fix.json res_fix3 fix ;;
  esac
  echo "STEP $s DONE $(date +%H:%M)" >> fix_evening.log
done
