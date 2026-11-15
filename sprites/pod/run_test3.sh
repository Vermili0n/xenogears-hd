#!/usr/bin/env bash
# After LoRA v3 training: held-out evaluation, 2 seeds. v3 checkpoints on test3/jobs.json (v3 boards, heads, NPC boards),
# v2 baseline on test3/jobs_v2.json (v2 boards / blank board). Results in res_test3/<run>/<tag>/; log test3.log.
#   bash run_test3.sh [cfg]
cd /workspace
export HF_HOME=/workspace/hf
CFG=${1:-4}
O=output/xeno_klein_v3
for seed in 42 43; do
  python infer_pod.py --jobs test3/jobs.json --out res_test3/v3_cfg${CFG}_s$seed --crop --cfg $CFG --seed $seed \
    --lora $O/xeno_klein_v3_000001000.safetensors --lora $O/xeno_klein_v3_000001500.safetensors --lora $O/xeno_klein_v3.safetensors
  python infer_pod.py --jobs test3/jobs_v2.json --out res_test3/v2_cfg${CFG}_s$seed --crop --cfg $CFG --seed $seed \
    --lora xeno_klein_v2.safetensors
done
# more sampling steps (model card example uses 50): final v3, seed 42
python infer_pod.py --jobs test3/jobs.json --out res_test3/v3_cfg${CFG}_st50_s42 --crop --cfg $CFG --seed 42 --steps 50 \
  --lora $O/xeno_klein_v3.safetensors
pip install -q lpips >/dev/null 2>&1
python metrics_pod.py --set test3 --res res_test3 --out metrics_test3.json
echo TEST3 DONE
