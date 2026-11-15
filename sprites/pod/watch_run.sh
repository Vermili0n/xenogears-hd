#!/usr/bin/env bash
# Poll one pod render run; ONE line per event: errors, dead process, progress every 5 min, finish.
#   POD_JUMP=<JUMP_HOST> bash watch_run.sh <host> <port> <log> <result dir> <total images> <done marker>
H=$1; P=$2; LOG=$3; RES=$4; TOTAL=$5; MARK=$6
S="ssh -o ConnectTimeout=25 -o BatchMode=yes ${POD_JUMP:+-J $POD_JUMP} -p $P -i <HOME>/.ssh/<SSH_KEY> -o StrictHostKeyChecking=no root@$H"
fails=0; tick=0; last_err=""
while true; do
  r=$($S "cd /workspace
    alive=\$(pgrep -f '[i]nfer_pod.py' >/dev/null && echo 1 || echo 0)
    n=\$(find $RES -name '*.png' 2>/dev/null | wc -l)
    done_=\$(grep -c '$MARK' $LOG 2>/dev/null)
    err=\$(tr '\r' '\n' < $LOG 2>/dev/null | grep -E 'Traceback|out of memory|OutOfMemory|Killed|Error' | tail -1 | cut -c1-200)
    rate=\$(tr '\r' '\n' < $LOG 2>/dev/null | grep -oE '[0-9.]+s/img eta [0-9.]+h' | tail -1)
    echo \"A=\$alive|N=\$n|D=\${done_:-0}|E=\$err|R=\$rate\"" 2>/dev/null </dev/null)
  if [ -z "$r" ]; then
    fails=$((fails+1)); [ $fails -eq 3 ] && echo "POD UNREACHABLE: ssh failed 3 times in a row"
    sleep 60; continue
  fi
  [ $fails -ge 3 ] && echo "pod reachable again"; fails=0
  get() { echo "$r" | tr '|' '\n' | grep "^$1=" | cut -d= -f2-; }
  A=$(get A); N=$(get N); D=$(get D); E=$(get E); R=$(get R)
  if [ -n "$E" ] && [ "$E" != "$last_err" ]; then echo "RUN ERROR: $E"; last_err=$E; fi
  if [ "${D:-0}" -ge 1 ]; then echo "RUN DONE: $N/$TOTAL images"; exit 0; fi
  if [ "$A" = "0" ]; then echo "PROCESS DIED at $N/$TOTAL: ${E:-no error line}"; exit 1; fi
  tick=$((tick+1))
  [ $((tick % 5)) -eq 1 ] && echo "status OK: $N/$TOTAL images ${R:+($R)}"
  sleep 60
done
