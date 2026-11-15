#!/usr/bin/env bash
# Rented GPU pod (RunPod, PyTorch 2.8 template): train the FLUX.2 klein 4B edit LoRA on (sprite -> Gemini redraw) pairs.
#   bash train_pod.sh [steps] [base|distilled]   (expects /workspace/pod_bundle.zip; log -> /workspace/train.log)
# distilled: train on the 4-step FLUX.2-klein-4B itself (what the laptop runs in sd.cpp) instead of klein-base-4B
# Samples on held-out controls are written at every checkpoint: /workspace/output/xeno_klein/samples
set -e
STEPS=${1:-1500}
VARIANT=${2:-base}
export PIP_BREAK_SYSTEM_PACKAGES=1  # image python is "externally managed" (PEP 668); torch lives there
W=/workspace
cd $W
[ -d data ] || { mkdir -p data && cd data && unzip -q ../pod_bundle.zip && cd ..; }
echo "pairs: $(ls data/aitk_data/target/*.png | wc -l)  eval: $(ls data/eval/*.png | wc -l)"
nvidia-smi --query-gpu=name,memory.total --format=csv
python -c "import torch; print(torch.__version__, torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())"

[ -d ai-toolkit ] || git clone --depth 1 https://github.com/ostris/ai-toolkit.git
if [ ! -f .deps_ok ]; then
  cat ai-toolkit/requirements*.txt | grep -v -i -E '^-r|^(torch|torchvision|torchaudio|torchcodec)([=<>~ ;]|$)' > req.txt || true
  pip install -q -r req.txt
  pip install -q hf_transfer
  touch .deps_ok
fi
grep -rn "ctrl_img" ai-toolkit/toolkit/config_modules.py | head -3 || echo "WARN: no ctrl_img in sample config"

FEI='redraw this pixel-art sprite as a clean 90s anime illustration of Fei, same pose and silhouette, flat magenta background'
NPC='redraw this pixel-art sprite as a clean 90s anime illustration, same pose, colors and silhouette, flat magenta background'
SAMPLES=""
for f in data/eval/*.png; do
  n=$(basename $f .png)
  case $n in fei_*) P=$FEI;; *) P=$NPC;; esac
  SAMPLES="$SAMPLES
          - prompt: \"$P\"
            ctrl_img: \"$W/$f\""
done

cat > xeno_klein.yaml <<EOF
---
job: extension
config:
  name: "xeno_klein"
  process:
    - type: "sd_trainer"
      training_folder: "$W/output"
      device: "cuda:0"
      network:
        type: "lora"
        linear: 32
        linear_alpha: 32
      save:
        dtype: "float16"
        save_every: 250
        max_step_saves_to_keep: 10
      datasets:
        - folder_path: "$W/data/aitk_data/target"
          control_path: "$W/data/aitk_data/control"
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
        sample_every: 250
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
  # ai-toolkit takes a local transformer file as name_or_path (flux2_model.py: os.path.exists -> no hub lookup)
  TF=$(python -c "from huggingface_hub import hf_hub_download as d; print(d('black-forest-labs/FLUX.2-klein-4B', 'flux-2-klein-4b.safetensors'))")
  sed -i "s#name_or_path: .*#name_or_path: \"$TF\"#; s#sample_steps: 28#sample_steps: 4#; s#guidance_scale: 4#guidance_scale: 1#" $W/xeno_klein.yaml
  grep -n "name_or_path\|sample_steps\|guidance_scale" $W/xeno_klein.yaml
fi
cd ai-toolkit
nohup python run.py $W/xeno_klein.yaml > $W/train.log 2>&1 &
echo "started pid $!"
