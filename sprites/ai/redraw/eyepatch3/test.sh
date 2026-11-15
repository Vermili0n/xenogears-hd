#!/usr/bin/env bash
# 4 heads, one seed: does the repaint work at all? Runs in the foreground, ~1 min.
cd /workspace
export PYTHONPATH=/workspace HF_HOME=/workspace/hf
python repaint_pod.py --jobs redraw/eyepatch3/jobs_test.json --out redraw/eyepatch3/test_7 --seed 7 --lora lora/xeno_klein_v4.safetensors --neg "goggles, visor, sunglasses, mask, both eyes covered, green eyes, brown eyes" 2>&1 | grep -v "it/s"
ls redraw/eyepatch3/test_7/v4 | wc -l
echo TEST_DONE
