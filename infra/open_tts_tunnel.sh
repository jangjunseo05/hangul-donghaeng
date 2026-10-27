#!/usr/bin/env bash
set -euo pipefail
: "${GPU_SSH_ALIAS:?Set the approved L40S SSH alias in this shell, never in tracked files}"
# Separate from open_model_tunnel.sh so a TTS outage never takes the model tunnel down.
# Default 9100 = infra/tts_postfx.py (Magpie + approved post-processing); 9000 = raw Magpie.
# Broker then uses TTS_BASE_URL=http://127.0.0.1:${TTS_TUNNEL_PORT} (plain HTTP only on loopback).
TUNNEL_BIND=127.0.0.1
TTS_TUNNEL_PORT="${TTS_TUNNEL_PORT:-9100}"
case "$TTS_TUNNEL_PORT" in (*[!0-9]*|'') echo "TTS_TUNNEL_PORT must be a port number" >&2; exit 2;; esac

exec ssh -T -N -S none -o ControlMaster=no -o ControlPath=none -o ForkAfterAuthentication=no -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L "$TUNNEL_BIND:$TTS_TUNNEL_PORT:127.0.0.1:$TTS_TUNNEL_PORT" "$GPU_SSH_ALIAS"
