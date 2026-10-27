#!/usr/bin/env bash
set -euo pipefail
: "${GPU_SSH_ALIAS:?Set the approved L40S SSH alias in this shell, never in tracked files}"
# Separate from open_model_tunnel.sh so a TTS outage never takes the model tunnel down.
# Broker then uses TTS_BASE_URL=http://127.0.0.1:9000 (plain HTTP is accepted only on loopback).
TUNNEL_BIND=127.0.0.1

exec ssh -T -N -S none -o ControlMaster=no -o ControlPath=none -o ForkAfterAuthentication=no -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L "$TUNNEL_BIND:9000:127.0.0.1:9000" "$GPU_SSH_ALIAS"
