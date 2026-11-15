#!/usr/bin/env bash
# Pod B after its production shards 1-3 are DONE (29.10 rebalance): the TAIL of shard 0's remaining v4 jobs
# (prod/jobs_tail0.json) on the 3 free GPUs, into res_prod like the production run (prod_sync.pull takes it from here).
# rebal_state = running / done for the watcher (it holds the final download until done). Logs tail_<i>.log.
#   setsid nohup bash tail_run_b.sh </dev/null >tail_run_b.out 2>&1 &
cd /workspace
for d in prod_1.log prod_2.log prod_3.log; do
  grep -q "PROD .* DONE" "$d" || { echo "production shard not done: $d - refusing to start"; exit 1; }
done
echo running > rebal_state
export HF_HOME=/workspace/hf
for i in 0 1 2; do
  (CUDA_VISIBLE_DEVICES=$i python infer_pod.py --jobs prod/jobs_tail0.json --out res_prod --crop --cfg 4 --seed 42 \
     --shard $i/3 --lora lora/xeno_klein_v4.safetensors > tail_$i.log 2>&1; echo "TAIL $i DONE" >> tail_$i.log) &
done
wait
echo done > rebal_state
