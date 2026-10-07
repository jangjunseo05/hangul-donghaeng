#!/usr/bin/env bash
set -euo pipefail
: "${GPU_SSH_ALIAS:?Set the existing approved SSH alias in this shell, never in tracked files}"
# The measured local gateway resolves host.openshell.internal to WSL loopback.
TUNNEL_BIND=127.0.0.1

exec ssh -T -N -S none -o ControlMaster=no -o ControlPath=none -o ForkAfterAuthentication=no -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L "$TUNNEL_BIND:8001:127.0.0.1:8001" "$GPU_SSH_ALIAS"
