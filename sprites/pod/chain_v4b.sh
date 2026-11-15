#!/usr/bin/env bash
# On the pod: LoRA v4 training -> held-out test (test3). Logs: setup.log, train.log, test4.log
cd /workspace
bash train_pod_v4.sh 4400 > setup.log 2>&1
sleep 60
until [ -f output/xeno_klein_v4/xeno_klein_v4.safetensors ] && ! pgrep -f "[p]ython run.py" > /dev/null; do sleep 60; done
pip install -q "git+https://github.com/huggingface/diffusers" lpips > pipdiff.log 2>&1
bash run_test4.sh > test4.log 2>&1
