#!/usr/bin/env bash
# After LoRA v4 training: the same held-out test3 as v3 (2 seeds, cfg 4, 28 steps), checkpoints 3500 + final.
# v3 results on this set are kept locally (pod/report/test3_final) and compared with metrics_test4.json.
cd /workspace
export HF_HOME=/workspace/hf
O=output/xeno_klein_v4
for seed in 42 43; do
  # one process: two copies of the pipeline (~17 GB each) do not fit in 32 GB, and one GPU gains little from two
  python infer_pod.py --jobs test3/jobs.json --out res_test4/v4_cfg4_s$seed --crop --cfg 4 --seed $seed \
    --lora $O/xeno_klein_v4_000003500.safetensors --lora $O/xeno_klein_v4.safetensors > test4_${seed}_0.log 2>&1
done
python metrics_pod.py --set test3 --res res_test4 --out metrics_test4.json > metrics4.log 2>&1
echo TEST4 DONE
