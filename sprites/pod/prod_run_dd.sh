#!/usr/bin/env bash
# Production render (deduplicated queue, see tools/prod_dedup.py) on one GPU: shard i of n of the v4 jobs (heroes, story, massovka), then the same shard of the
# gear jobs with LoRA v2. Resumable (infer_pod skips existing outputs) - rerun the same command after a restart.
#   bash prod_run_dd.sh <shard i> <shards n> <gpu index>      e.g. bash prod_run_dd.sh 0 4 0
# Outputs: /workspace/res_prod/v4/<name>.png, /workspace/res_prod/v2/<name>.png; log prod_<i>.log, marker PROD <i> DONE
cd /workspace
export HF_HOME=/workspace/hf CUDA_VISIBLE_DEVICES=$3
I=$1; N=$2
python infer_pod.py --jobs prod/jobs_v4_dd.json --out res_prod --crop --cfg 4 --seed 42 --shard $I/$N \
  --lora lora/xeno_klein_v4.safetensors >> prod_$I.log 2>&1
python infer_pod.py --jobs prod/jobs_v2_dd.json --out res_prod --crop --cfg 4 --seed 42 --shard $I/$N \
  --lora lora/xeno_klein_v2.safetensors >> prod_$I.log 2>&1
echo "PROD $I DONE" >> prod_$I.log
