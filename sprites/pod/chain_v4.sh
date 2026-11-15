#!/usr/bin/env bash
# On the pod: pilot render -> LoRA v4 training -> held-out test. Logs: setup.log, train.log, test4.log
cd /workspace
until grep -q "PILOT DONE" run_pilot.log 2>/dev/null; do sleep 20; done
bash train_pod_v4.sh 4400 > setup.log 2>&1
sleep 60
until [ -f output/xeno_klein_v4/xeno_klein_v4.safetensors ] && ! pgrep -f "[p]ython run.py" > /dev/null; do sleep 60; done
bash run_test4.sh > test4.log 2>&1
