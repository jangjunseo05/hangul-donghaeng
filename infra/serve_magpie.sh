#!/usr/bin/env bash
set -euo pipefail
# PLAN ONLY until the orchestrator approves: run on the L40S GPU host (never the shared RTX 4090 lab host).
# Starts NVIDIA Magpie TTS Multilingual (Speech NIM >= 26.07, ko-KR support) bound to host loopback.
# Requires NGC_API_KEY in the shell (docker login nvcr.io -u '$oauthtoken'); never write it to files.
# Image name/tag, ports 9000 (HTTP) / 50051 (gRPC) and the NIM cache path follow the Speech NIM docs
# and are unverified against this host. Check free VRAM first: vLLM reserves 0.85 of the L40S.
: "${NGC_API_KEY:?Export NGC_API_KEY in this shell only}"
: "${MAGPIE_IMAGE:?Set MAGPIE_IMAGE=nvcr.io/nim/nvidia/magpie-tts-multilingual:<tag from NGC>}"
NAME=hangul-magpie-01
RUNTIME_DIR="$HOME/hangul-donghaeng-runtime"
MIN_FREE_MIB="${MAGPIE_MIN_FREE_MIB:-6000}"
if docker container inspect "$NAME" >/dev/null 2>&1; then
    echo "Refusing to replace existing $NAME; inspect it first."
    exit 2
fi
free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0 | tr -d ' ')
if [ "$free_mib" -lt "$MIN_FREE_MIB" ]; then
    echo "Only ${free_mib} MiB free on GPU 0 (< ${MIN_FREE_MIB}). Do not stop vLLM from this script;"
    echo "plan B (restart vLLM with --gpu-memory-utilization 0.70) needs orchestrator approval."
    exit 3
fi
mkdir -p "$RUNTIME_DIR/nim-cache"
docker run -d --name "$NAME" --gpus device=0 --shm-size 2g \
  -e NGC_API_KEY \
  -v "$RUNTIME_DIR/nim-cache:/opt/nim/.cache" \
  -p 127.0.0.1:9000:9000 -p 127.0.0.1:50051:50051 \
  "$MAGPIE_IMAGE"
echo "Magpie container launched. Verify: curl -s 127.0.0.1:9000/v1/health/ready ; curl -s 127.0.0.1:9000/v1/audio/list_voices"
echo "Rollback: docker stop $NAME && docker rm $NAME"
