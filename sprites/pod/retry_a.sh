#!/usr/bin/env bash
# Pod A, 29.10 after its production shard: retries of the two hints that failed the test -
#   short_hair: m_7d47706ecb back frames with the TWIN's board (npc_42ee795e87, short hair) -> res_retry_hair
#   front: Fei "faces the viewer, head bowed" frames with 4 other seeds -> res_retry_s<seed>
#   (setsid nohup bash retry_a.sh </dev/null >retry_a.out 2>&1 &)
cd /workspace
export HF_HOME=/workspace/hf CUDA_VISIBLE_DEVICES=0
python infer_pod.py --jobs prod/jobs_retry_hair.json --out res_retry_hair --crop --cfg 4 --seed 42 \
  --lora lora/xeno_klein_v4.safetensors > retry_hair.log 2>&1
for s in 7 123 2024 31337; do
  python infer_pod.py --jobs prod/jobs_retry_front.json --out res_retry_s$s --crop --cfg 4 --seed $s \
    --lora lora/xeno_klein_v4.safetensors > retry_s$s.log 2>&1
done
echo RETRY DONE >> retry_hair.log
