#!/usr/bin/env bash
# Render progress of all seeds: bar, per seed, speed, time left. Add a number to refresh: progress.sh 20
D=/workspace/redraw/eyepatch3
PER=$(python3 -c "import json; print(len(json.load(open('$D/jobs.json'))))")
SEEDS="7 11 23 31"
TOTAL=$((PER * 4))

show() {
  local done=0 line=""
  for s in $SEEDS; do
    n=$(ls "$D/res_$s/v4" 2>/dev/null | grep -c png)
    done=$((done + n))
    line="$line  seed $s: $n/$PER"
  done
  local pct=$((done * 100 / TOTAL)) fill=$((done * 40 / TOTAL))
  local bar
  bar=$(printf '%*s' "$fill" '' | tr ' ' '#')$(printf '%*s' "$((40 - fill))" '' | tr ' ' '.')
  echo "[$bar] $done/$TOTAL  $pct%  left: $((TOTAL - done))"
  echo "$line"
  # speed from the file times of the whole run
  local first last
  first=$(find "$D"/res_*/v4 -name '*.png' -printf '%T@\n' 2>/dev/null | sort -n | head -1)
  last=$(find "$D"/res_*/v4 -name '*.png' -printf '%T@\n' 2>/dev/null | sort -n | tail -1)
  if [ "$done" -ge 2 ]; then
    python3 - "$first" "$last" "$done" "$TOTAL" <<'EOF'
import sys, time
first, last, done, total = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
per = (last - first) / (done - 1)
left = (total - done) * per
print(f"speed: {per:.1f} s/picture  time left: ~{int(left // 60)} min  last picture {int(time.time() - last)} s ago")
EOF
  fi
  if grep -q RENDER_DONE "$D/infer.log" 2>/dev/null; then
    echo "DONE - download the result"
  elif ! pgrep -f '[r]epaint_pod.py' >/dev/null; then
    echo "render is NOT running"
    grep -iE 'error|traceback' "$D/infer.log" 2>/dev/null | tail -2
  fi
}

if [ -n "$1" ]; then
  while true; do clear; date '+%H:%M:%S'; show; grep -q RENDER_DONE "$D/infer.log" 2>/dev/null && break; sleep "$1"; done
else
  show
fi
