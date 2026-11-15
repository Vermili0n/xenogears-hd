#!/usr/bin/env bash
# Production render watcher (2 pods, 4 GPUs): a progress line on the clock every EVERY minutes (:00/:20/:40 for 20) -
# images done / total, rate, ETA; errors and dead processes immediately. Exits when all 4 "PROD i DONE" markers exist.
# The rate is measured between progress lines through a state file, so it survives restarts of the watcher.
#   bash watch_prod.sh <total images> [EVERY minutes, default 5]
TOTAL=${1:-45696}
EVERY=${2:-5}
STATE=<XENO_SPRITES>/pod/report/.watch_prod_state
A="ssh -o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=no -p <POD_PORT> -i <HOME>/.ssh/<SSH_KEY> root@<POD_HOST>"
B="ssh -o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=no -p <POD_PORT> -i <HOME>/.ssh/<SSH_KEY> root@<POD_HOST>"
Q='cd /workspace; n=$(find res_prod -name "*.png" 2>/dev/null | wc -l); p=$(pgrep -f "[i]nfer_pod" | wc -l); d=$(cat prod_*.log 2>/dev/null | grep -c "PROD .* DONE"); e=$(cat prod_*.log 2>/dev/null | tr "\r" "\n" | grep -E "Traceback|out of memory|OutOfMemory|Killed|Error" | tail -1 | cut -c1-150); echo "$n|$p|$d|$e"'
lasterr=""; lastslot=$(( $(date +%s) / (EVERY * 60) ))  # first line at the next boundary
while true; do
  ra=$($A "$Q" 2>/dev/null </dev/null); rb=$($B "$Q" 2>/dev/null </dev/null)
  [ -z "$ra" ] && echo "pod A unreachable"; [ -z "$rb" ] && echo "pod B unreachable"
  IFS='|' read -r na pa da ea <<< "$ra"; IFS='|' read -r nb pb db eb <<< "$rb"
  n=$(( ${na:-0} + ${nb:-0} )); done_=$(( ${da:-0} + ${db:-0} ))
  err="${ea}${eb}"; if [ -n "$err" ] && [ "$err" != "$lasterr" ]; then echo "RENDER ERROR: A[$ea] B[$eb]"; lasterr=$err; fi
  if [ "$done_" -ge 4 ]; then echo "ALL 4 SHARDS DONE: $n/$TOTAL images"; exit 0; fi
  if [ -n "$ra" ] && [ "${pa:-0}" -eq 0 ] && [ "${da:-0}" -lt 1 ]; then echo "pod A: no render process and not done"; fi
  if [ -n "$rb" ] && [ "${pb:-0}" -lt $((3 - ${db:-0})) ]; then echo "pod B: only ${pb:-0} render processes (done ${db:-0}/3)"; fi
  now=$(date +%s); slot=$(( now / (EVERY * 60) ))   # boundaries fall on :00/:20/:40 (the timezone is whole hours)
  [ -f "$STATE" ] || echo "$now $n" > "$STATE"
  if [ "$slot" != "$lastslot" ]; then
    lastslot=$slot; rate=0; eta="?"
    if [ -f "$STATE" ]; then
      read -r t1 n1 < "$STATE"
      if [ $((now - t1)) -gt 120 ] && [ $n -gt $n1 ]; then
        rate=$(( (n - n1) * 3600 / (now - t1) )); eta=$(awk "BEGIN{printf \"%.1f\", ($TOTAL-$n)/$rate}")
      fi
    fi
    echo "$now $n" > "$STATE"
    echo "render: $n/$TOTAL images (A ${na:-?}, B ${nb:-?}) | ~$rate img/h | ETA ${eta} h | GPUs busy: A ${pa:-?}/1, B ${pb:-?}/3"
  fi
  sleep 60
done
