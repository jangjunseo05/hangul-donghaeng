#!/usr/bin/env bash
set -euo pipefail
# Run on the already-authorized GPU host. Does not create cloud resources.
MODEL_ID=nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16
IMAGE=vllm/vllm-openai@sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe
NAME=hangul-nemotron-01
RUNTIME_DIR="$HOME/hangul-donghaeng-runtime"
if docker container inspect "$NAME" >/dev/null 2>&1; then
    echo "Refusing to replace existing $NAME; inspect it first."
    exit 2
fi
mkdir -p "$RUNTIME_DIR/model-cache"
docker pull "$IMAGE"
docker run -d --name "$NAME" --gpus device=0 --shm-size 4g \
  -p 127.0.0.1:8001:8001 \
  -v "$RUNTIME_DIR/model-cache:/root/.cache/huggingface" \
  "$IMAGE" --model "$MODEL_ID" --served-model-name "$MODEL_ID" \
  --revision ca9543b126e8bf3176916d3d305ccc415f89fd4d --trust-remote-code --dtype bfloat16 --max-model-len 8192 \
  --gpu-memory-utilization 0.85 --max-num-seqs 1 --enforce-eager \
  --limit-mm-per-prompt '{"image":1,"video":0}' \
  --host 0.0.0.0 --port 8001
echo "Model container launched; readiness and actual inference still require verification."
