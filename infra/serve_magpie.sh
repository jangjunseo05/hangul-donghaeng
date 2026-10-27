#!/usr/bin/env bash
set -euo pipefail
# Run on the dedicated L40S host (hangul-l40s) only, with orchestrator approval; never the shared lab hosts.
# Starts NVIDIA Magpie TTS Multilingual (Speech NIM 1.10.1 verified 2026-10-27, ko-KR) bound to host loopback.
# Deployment findings (orchestrator, 2026-10-27):
#  - vLLM must run with --gpu-memory-utilization 0.70 (serve_nemotron.sh GPU_MEM_UTIL); at 0.85 the
#    Magpie TensorRT build runs out of memory.
#  - Run with the image's default user: '-u $(id -u)' fails on /opt/nim/workspace permissions, so the
#    host cache directory must be writable by that user (chmod 777 below).
# Requires NGC_API_KEY in the shell (docker login nvcr.io -u '$oauthtoken'); never write it to files.
# Verified: POST /v1/audio/synthesize multipart (language, text, voice) -> 200 audio/wav;
# voice ids look like Magpie-Multilingual.KO-KR.Aria.
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
    echo "Restart vLLM with GPU_MEM_UTIL=0.70 (serve_nemotron.sh) first; that needs orchestrator approval."
    exit 3
fi
mkdir -p "$RUNTIME_DIR/nim-cache"
chmod 777 "$RUNTIME_DIR/nim-cache"  # the container's default user must write the model cache
docker run -d --name "$NAME" --gpus device=0 --shm-size 2g \
  -e NGC_API_KEY \
  -v "$RUNTIME_DIR/nim-cache:/opt/nim/.cache" \
  -p 127.0.0.1:9000:9000 -p 127.0.0.1:50051:50051 \
  "$MAGPIE_IMAGE"
echo "Magpie container launched. Verify: curl -s 127.0.0.1:9000/v1/health/ready ; curl -s 127.0.0.1:9000/v1/audio/list_voices"
echo "Rollback: docker stop $NAME && docker rm $NAME"
