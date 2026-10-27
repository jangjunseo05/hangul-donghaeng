#!/usr/bin/env bash
set -euo pipefail
# Run on hangul-l40s only (orchestrator approval). Starts/restarts infra/tts_postfx.py on 127.0.0.1:9100
# in front of Magpie (127.0.0.1:9000). Restart-safe: stops only the process recorded in its own pidfile.
#   scp infra/tts_postfx.py infra/serve_tts_postfx.sh hangul-l40s:~/hangul-donghaeng-runtime/tts-postfx/
#   ssh hangul-l40s 'bash ~/hangul-donghaeng-runtime/tts-postfx/serve_tts_postfx.sh'
DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-$HOME/hangul-donghaeng-runtime/tts-postfx}"
PORT="${TTS_POSTFX_PORT:-9100}"
PIDFILE="$RUNTIME_DIR/tts-postfx.pid"
LOG="$RUNTIME_DIR/tts-postfx.log"
mkdir -p "$RUNTIME_DIR"
command -v ffmpeg >/dev/null || echo "WARNING: ffmpeg not on PATH; audio will pass through unfiltered."
if [ -f "$PIDFILE" ]; then
    old="$(cat "$PIDFILE")"
    if kill -0 "$old" 2>/dev/null && tr '\0' ' ' < "/proc/$old/cmdline" | grep -q "tts_postfx.py"; then
        kill "$old"
        for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$old" 2>/dev/null || break; sleep 0.5; done
    fi
    rm -f "$PIDFILE"
fi
if ss -ltn "sport = :$PORT" | grep -q LISTEN; then
    echo "Port $PORT is held by another process; not starting." >&2
    exit 2
fi
TTS_POSTFX_PORT="$PORT" nohup python3 -u "$DIR/tts_postfx.py" >>"$LOG" 2>&1 &
echo $! > "$PIDFILE"
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s -m 2 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/v1/health/ready" | grep -q 200; then
        echo "tts-postfx ready on 127.0.0.1:$PORT (pid $(cat "$PIDFILE")); log $LOG"
        exit 0
    fi
    sleep 1
done
echo "tts-postfx did not become ready; see $LOG" >&2
exit 3
