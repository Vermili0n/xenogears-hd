#!/usr/bin/env bash
# LoRA v3 on a rented pod (RTX 4090): FLUX.2 klein base 4B edit LoRA, sprite frame + board -> redraw, masked loss.
#   bash train_pod_v3.sh [steps]     (expects /workspace/pod_bundle_v3.zip; logs -> /workspace/setup.log, train.log)
# Bundle: pairs_v3/{control,target(+txt),mask}, boards/<hash>.png + ref_map.json (-> pairs_v3/ref), eval/samples.json
# + eval/<name>_{c,r}.png. Optional stage 0 before training: if /workspace/xeno_klein_v2.safetensors and test2/ exist,
# the guidance sweep on v2 runs first (results in res_sweep/, log sweep.log).
set -e
STEPS=${1:-2000}
export PIP_BREAK_SYSTEM_PACKAGES=1  # image python is "externally managed" (PEP 668); torch lives there
W=/workspace
cd $W
if [ ! -d data ]; then
  mkdir -p data && cd data && unzip -q ../pod_bundle_v3.zip
  python -c "import json,os,shutil; m=json.load(open('ref_map.json')); os.makedirs('pairs_v3/ref',exist_ok=True); [shutil.copyfile(f'boards/{h}.png', f'pairs_v3/ref/{n}') for n,h in m.items()]"
  cd ..
fi
echo "triplets: $(ls data/pairs_v3/target/*.png | wc -l)  refs: $(ls data/pairs_v3/ref | wc -l)  masks: $(ls data/pairs_v3/mask | wc -l)"
nvidia-smi --query-gpu=name,memory.total --format=csv
python -c "import torch; print(torch.__version__, torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())"

[ -d ai-toolkit ] || git clone --depth 1 https://github.com/ostris/ai-toolkit.git
if [ ! -f .deps_ok ]; then
  cat ai-toolkit/requirements*.txt | grep -v -i -E '^-r|^(torch|torchvision|torchaudio|torchcodec)([=<>~ ;]|$)' > req.txt || true
  pip install -q -r req.txt
  pip install -q hf_transfer
  touch .deps_ok
fi
export HF_HOME=$W/hf HF_HUB_ENABLE_HF_TRANSFER=1

if [ -f xeno_klein_v2.safetensors ] && [ -d test2 ] && [ ! -f .sweep_done ]; then
  echo "stage 0: guidance sweep on v2"
  for run in "1 42" "1 43" "1.5 42" "1.5 43" "2 42" "2 43" "3 42" "3 43" "4 43"; do  # cfg 4 seed 42 = res_test2/crop/v2 (v2 pod)
    set -- $run
    python infer_pod.py --jobs test2/jobs.json --out res_sweep/cfg$1_s$2 --crop --cfg $1 --seed $2 \
      --lora xeno_klein_v2.safetensors >> sweep.log 2>&1
  done
  touch .sweep_done
  echo "stage 0 done"
fi

SAMPLES=$(python - <<'PY'
import json
for s in json.load(open('/workspace/data/eval/samples.json')):
    print(f'          - prompt: {json.dumps(s["prompt"])}')
    print(f'            ctrl_img_1: "/workspace/data/eval/{s["name"]}_c.png"')
    print(f'            ctrl_img_2: "/workspace/data/eval/{s["name"]}_r.png"')
PY
)

cat > xeno_klein_v3.yaml <<EOF
---
job: extension
config:
  name: "xeno_klein_v3"
  process:
    - type: "sd_trainer"
      training_folder: "$W/output"
      device: "cuda:0"
      network:
        type: "lora"
        linear: 64
        linear_alpha: 64
      save:
        dtype: "float16"
        save_every: 500
        max_step_saves_to_keep: 10
      datasets:
        - folder_path: "$W/data/pairs_v3/target"
          control_path_1: "$W/data/pairs_v3/control"
          control_path_2: "$W/data/pairs_v3/ref"
          mask_path: "$W/data/pairs_v3/mask"
          mask_min_value: 0.15
          caption_ext: "txt"
          caption_dropout_rate: 0.05
          cache_latents_to_disk: true
          flip_x: false
          resolution: [ 512 ]
      train:
        batch_size: 4
        steps: $STEPS
        gradient_accumulation_steps: 1
        train_unet: true
        train_text_encoder: false
        gradient_checkpointing: true
        noise_scheduler: "flowmatch"
        optimizer: "adamw8bit"
        lr: 1e-4
        timestep_type: "weighted"
        dtype: "bf16"
        cache_text_embeddings: false
        unload_text_encoder: false
        skip_first_sample: true
        ema_config:
          use_ema: true
          ema_decay: 0.999
      model:
        name_or_path: "black-forest-labs/FLUX.2-klein-base-4B"
        arch: "flux2_klein_4b"
        quantize: false
        quantize_te: false
      sample:
        sampler: "flowmatch"
        sample_every: 500
        width: 512
        height: 512
        samples:
$SAMPLES
        neg: ""
        seed: 42
        walk_seed: false
        guidance_scale: 4
        sample_steps: 28
meta:
  name: "[name]"
  version: "1.0"
EOF
cd ai-toolkit
nohup python run.py $W/xeno_klein_v3.yaml > $W/train.log 2>&1 &
echo "started pid $!"
