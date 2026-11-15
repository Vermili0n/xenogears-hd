#!/usr/bin/env bash
# LoRA v2 on a rented pod: FLUX.2 klein 4B edit LoRA, two control images (sprite frame + character board) -> redraw.
#   bash train_pod_v2.sh [steps] [base|distilled]   (expects /workspace/pod_bundle_v2.zip; log -> /workspace/train.log)
# Bundle: pairs_v2/{control,ref,target} (+ target/*.txt captions), pairs_v2/split.json, eval/<name>_{c,r}.png
# Held-out samples are rendered at every checkpoint into /workspace/output/xeno_klein_v2/samples
set -e
STEPS=${1:-2500}
VARIANT=${2:-base}
export PIP_BREAK_SYSTEM_PACKAGES=1  # image python is "externally managed" (PEP 668); torch lives there
W=/workspace
cd $W
if [ ! -d data ]; then
  mkdir -p data && cd data && unzip -q ../pod_bundle_v2.zip
  # one board per character in the bundle -> one ref image per triplet (ai-toolkit pairs control files by name)
  python -c "import json,os,shutil; m=json.load(open('ref_map.json')); os.makedirs('pairs_v2/ref',exist_ok=True); [shutil.copyfile(f'boards/{h}.png', f'pairs_v2/ref/{n}') for n,h in m.items()]"
  cd ..
fi
echo "triplets: $(ls data/pairs_v2/target/*.png | wc -l)  eval: $(ls data/eval/*_c.png | wc -l)"
nvidia-smi --query-gpu=name,memory.total --format=csv
python -c "import torch; print(torch.__version__, torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())"

[ -d ai-toolkit ] || git clone --depth 1 https://github.com/ostris/ai-toolkit.git
if [ ! -f .deps_ok ]; then
  cat ai-toolkit/requirements*.txt | grep -v -i -E '^-r|^(torch|torchvision|torchaudio|torchcodec)([=<>~ ;]|$)' > req.txt || true
  pip install -q -r req.txt
  pip install -q hf_transfer
  touch .deps_ok
fi

CAP='redraw this pixel-art sprite as a clean 90s anime illustration of the character shown in the second image, same pose and silhouette, flat magenta background'
SAMPLES=""
for f in data/eval/*_c.png; do
  n=$(basename $f _c.png)
  SAMPLES="$SAMPLES
          - prompt: \"$CAP\"
            ctrl_img_1: \"$W/data/eval/${n}_c.png\"
            ctrl_img_2: \"$W/data/eval/${n}_r.png\""
done

cat > xeno_klein_v2.yaml <<EOF
---
job: extension
config:
  name: "xeno_klein_v2"
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
        - folder_path: "$W/data/pairs_v2/target"
          control_path_1: "$W/data/pairs_v2/control"
          control_path_2: "$W/data/pairs_v2/ref"
          caption_ext: "txt"
          caption_dropout_rate: 0.05
          cache_latents_to_disk: true
          resolution: [ 512 ]
      train:
        batch_size: 2
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
        cache_text_embeddings: true
        unload_text_encoder: true
        skip_first_sample: true
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
        samples:$SAMPLES
        neg: ""
        seed: 42
        walk_seed: false
        guidance_scale: 4
        sample_steps: 28
meta:
  name: "[name]"
  version: "1.0"
EOF
export HF_HOME=$W/hf HF_HUB_ENABLE_HF_TRANSFER=1
if [ "$VARIANT" = "distilled" ]; then
  TF=$(python -c "from huggingface_hub import hf_hub_download as d; print(d('black-forest-labs/FLUX.2-klein-4B', 'flux-2-klein-4b.safetensors'))")
  sed -i "s#name_or_path: .*#name_or_path: \"$TF\"#; s#sample_steps: 28#sample_steps: 4#; s#guidance_scale: 4#guidance_scale: 1#" $W/xeno_klein_v2.yaml
fi
cd ai-toolkit
nohup python run.py $W/xeno_klein_v2.yaml > $W/train.log 2>&1 &
echo "started pid $!"
