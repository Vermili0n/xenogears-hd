#!/usr/bin/env bash
# After training: compare checkpoints on the test set (crop) + the last one without crop; log -> /workspace/test2.log
cd /workspace
export HF_HOME=/workspace/hf
O=output/xeno_klein_v2
python infer_pod.py --jobs test2/jobs.json --out res_test2/crop --crop \
  --lora $O/xeno_klein_v2_000001500.safetensors --lora $O/xeno_klein_v2_000002000.safetensors --lora $O/xeno_klein_v2.safetensors
python infer_pod.py --jobs test2/jobs.json --out res_test2/full --lora $O/xeno_klein_v2.safetensors
echo TEST2 DONE
