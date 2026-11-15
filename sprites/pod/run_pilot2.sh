#!/usr/bin/env bash
# Pilot render on the pod: wait for setup_infer.sh, then 2 parallel shards of render_pilot2/jobs.json with LoRA v3.
cd /workspace
export HF_HOME=/workspace/hf
until grep -q SETUP_OK setup_infer.log; do sleep 10; done
for i in 0 1; do
  python infer_pod.py --jobs render_pilot2/jobs.json --out res_pilot2 --crop --cfg 4 --seed 42 --shard $i/2 \
    --lora xeno_klein_v3.safetensors > pilot2_$i.log 2>&1 &
done
wait
echo PILOT2 DONE
