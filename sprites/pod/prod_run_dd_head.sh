#!/usr/bin/env bash
# Pod A after the 29.10 rebalance: only the HEAD of shard 0's remaining v4 jobs (prod/jobs_head0.json), then shard 0's
# gears (LoRA v2), then the usual marker. The tail of shard 0 is rendered on pod B (pod/tail_run_b.sh).
# The file name keeps the watcher's wrapper count (pgrep -f "[p]rod_run_dd") working. Resumable like prod_run_dd.sh.
#   setsid nohup bash prod_run_dd_head.sh </dev/null >head_run.out 2>&1 &
cd /workspace
export HF_HOME=/workspace/hf CUDA_VISIBLE_DEVICES=0
python infer_pod.py --jobs prod/jobs_head0.json --out res_prod --crop --cfg 4 --seed 42 \
  --lora lora/xeno_klein_v4.safetensors >> prod_0.log 2>&1
python infer_pod.py --jobs prod/jobs_v2_dd.json --out res_prod --crop --cfg 4 --seed 42 --shard 0/4 \
  --lora lora/xeno_klein_v2.safetensors >> prod_0.log 2>&1
echo "PROD 0 DONE" >> prod_0.log
