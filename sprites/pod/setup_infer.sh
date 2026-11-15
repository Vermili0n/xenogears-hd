#!/usr/bin/env bash
# Inference-only pod setup: diffusers (Flux2KleinPipeline) + FLUX.2 klein base 4B weights. Log: /workspace/setup_infer.log
set -e
export PIP_BREAK_SYSTEM_PACKAGES=1 HF_HOME=/workspace/hf HF_HUB_ENABLE_HF_TRANSFER=1
pip install -q "git+https://github.com/huggingface/diffusers" transformers accelerate peft safetensors sentencepiece hf_transfer lpips
python -c "from diffusers import Flux2KleinPipeline; import diffusers; print(diffusers.__version__)"
# the repo root also holds a 7.75 GB single-file copy of the transformer: diffusers does not read it
python -c "from huggingface_hub import snapshot_download as s; print(s('black-forest-labs/FLUX.2-klein-base-4B', ignore_patterns=['flux-2-klein-*.safetensors']))"
echo SETUP_OK
