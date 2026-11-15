#!/usr/bin/env bash
# Poll the pod after training (chain_v4b.sh: pip diffusers -> run_test4.sh -> metrics); ONE line per event:
# pip / test errors, OOM, dead test, progress every 5 min, finish (TEST4 DONE).
#   POD_JUMP=<JUMP_HOST> bash watch_test.sh <host> <port> [expected images per seed folder]
H=$1; P=$2; EXP=${3:-0}
S="ssh -o ConnectTimeout=25 -o BatchMode=yes ${POD_JUMP:+-J $POD_JUMP} -p $P -i <HOME>/.ssh/<SSH_KEY> -o StrictHostKeyChecking=no root@$H"
fails=0; tick=0; last_err=""; seen_start=0
while true; do
  r=$($S 'cd /workspace
    pip=$(pgrep -f "[p]ip install" >/dev/null && echo 1 || echo 0)
    inf=$(pgrep -f "[i]nfer_pod.py" >/dev/null && echo 1 || echo 0)
    met=$(pgrep -f "[m]etrics_pod.py" >/dev/null && echo 1 || echo 0)
    done_=$(grep -c "TEST4 DONE" test4.log 2>/dev/null)
    n42=$(find res_test4/v4_cfg4_s42 -name "*.png" 2>/dev/null | wc -l)
    n43=$(find res_test4/v4_cfg4_s43 -name "*.png" 2>/dev/null | wc -l)
    err=$(cat test4_*_0.log pipdiff.log metrics4.log 2>/dev/null | tr "\r" "\n" | grep -E "Traceback|out of memory|OutOfMemory|Killed|Error" | tail -1 | cut -c1-200)
    echo "PIP=$pip|INF=$inf|MET=$met|DONE=${done_:-0}|N42=$n42|N43=$n43|ERR=$err"' 2>/dev/null </dev/null)
  if [ -z "$r" ]; then
    fails=$((fails+1)); [ $fails -eq 3 ] && echo "POD UNREACHABLE: ssh failed 3 times in a row"
    sleep 60; continue
  fi
  [ $fails -ge 3 ] && echo "pod reachable again"; fails=0
  get() { echo "$r" | tr '|' '\n' | grep "^$1=" | cut -d= -f2-; }
  PIP=$(get PIP); INF=$(get INF); MET=$(get MET); DONE=$(get DONE); N42=$(get N42); N43=$(get N43); ERR=$(get ERR)
  if [ -n "$ERR" ] && [ "$ERR" != "$last_err" ]; then echo "TEST ERROR: $ERR"; last_err=$ERR; fi
  [ "$INF" = "1" ] && [ $seen_start -eq 0 ] && { echo "test rendering started"; seen_start=1; }
  if [ "${DONE:-0}" -ge 1 ]; then echo "TEST4 DONE: seed42 $N42, seed43 $N43 images, metrics written"; exit 0; fi
  if [ $seen_start -eq 1 ] && [ "$INF" = "0" ] && [ "$MET" = "0" ] && [ "$PIP" = "0" ] && [ "${DONE:-0}" -eq 0 ]; then
    sleep 20; continue  # between the two seeds / before metrics; the next poll decides
  fi
  tick=$((tick+1))
  if [ $((tick % 5)) -eq 1 ]; then
    if [ "$PIP" = "1" ]; then echo "status OK: installing diffusers for the test"
    elif [ "$MET" = "1" ]; then echo "status OK: computing metrics (LPIPS)"
    elif [ "$INF" = "1" ]; then echo "status OK: test rendering seed42 $N42${EXP:+/$EXP}, seed43 $N43${EXP:+/$EXP}"
    else echo "status OK: waiting for the test to start"; fi
  fi
  sleep 60
done
