#!/usr/bin/env bash
# Poll the training pod once a minute; print ONE line per event (Monitor tool event stream):
# setup/train errors, OOM, dead process, stalled log (> STALL s), pod unreachable, each new checkpoint, finish.
#   bash watch_pod.sh <host> <port> [total_steps] [run name, default xeno_klein_v2]
H=$1; P=$2; TOTAL=${3:-1500}; NAME=${4:-xeno_klein_v2}; STALL=480
S="ssh -o ConnectTimeout=25 -o BatchMode=yes ${POD_JUMP:+-J $POD_JUMP} -p $P -i <HOME>/.ssh/<SSH_KEY> -o StrictHostKeyChecking=no root@$H"
fails=0; last_ck=-1; last_err=0; last_state=""; started=0; tick=0
while true; do
  r=$($S 'cd /workspace
    alive=$(pgrep -f "[p]ython run.py" >/dev/null && echo 1 || echo 0)
    setup=$(grep -E "started pid|ERROR|FAILED|No such file" setup.log 2>/dev/null | tail -1 | tr -d "\r" | cut -c1-160)
    if [ -f train.log ]; then age=$(( $(date +%s) - $(stat -c %Y train.log) )); else age=-1; fi
    step=$(tr "\r" "\n" < train.log 2>/dev/null | grep -oE "[0-9]+/'"$TOTAL"' \[[^]]*\]" | tail -1)
    err=$(grep -cE "Traceback|CUDA out of memory|OutOfMemory|Killed|RuntimeError|Error:" train.log 2>/dev/null)
    errline=$(tr "\r" "\n" < train.log 2>/dev/null | grep -E "Traceback|out of memory|Killed|Error" | tail -1 | cut -c1-200)
    ck=$(ls output/'"$NAME"'/*.safetensors 2>/dev/null | wc -l)
    sw=$(tr "\r" "\n" < sweep.log 2>/dev/null | grep -E "Traceback|Error" | tail -1 | cut -c1-100)
    [ -z "$sw" ] && sw=$(for d in res_sweep/*/v2; do [ -d $d ] && echo "$(basename $(dirname $d)):$(ls $d | wc -l)"; done 2>/dev/null | tr "\n" " ")
    phase=$(tr "\r" "\n" < train.log 2>/dev/null | grep -vE "^\s*$" | tail -1 | cut -c1-120)
    echo "A=$alive|AGE=$age|CK=$ck|ERR=${err:-0}|STEP=$step|SETUP=$setup|EL=$errline|PH=$phase|SW=$sw"' 2>/dev/null </dev/null)
  if [ -z "$r" ]; then
    fails=$((fails+1)); [ $fails -eq 3 ] && echo "POD UNREACHABLE: ssh failed 3 times in a row"
    sleep 60; continue
  fi
  [ $fails -ge 3 ] && echo "pod reachable again"; fails=0
  get() { echo "$r" | tr '|' '\n' | grep "^$1=" | cut -d= -f2-; }
  A=$(get A); AGE=$(get AGE); CK=$(get CK); ERR=$(get ERR); STEP=$(get STEP); SETUP=$(get SETUP); EL=$(get EL); PH=$(get PH); SW=$(get SW)
  case "$SETUP" in
    *ERROR*|*FAILED*|*"No such file"*) [ "$last_state" != "setup_err" ] && echo "SETUP FAILED: $SETUP"; last_state=setup_err;;
    *"started pid"*) [ $started -eq 0 ] && echo "training process started"; started=1;;
  esac
  if [ "${ERR:-0}" -gt "$last_err" ]; then echo "TRAIN ERROR: $EL"; last_err=$ERR; fi
  if [ "$CK" -gt "$last_ck" ] && [ "$last_ck" -ge 0 ]; then echo "checkpoint $CK saved | $STEP"; fi
  last_ck=$CK
  if [ $started -eq 1 ] && [ "$A" = "0" ]; then
    if [ "$CK" -ge $((TOTAL / 500)) ]; then echo "TRAINING DONE: $CK checkpoints | $STEP"; exit 0; fi
    echo "PROCESS DIED (step: ${STEP:-none}) last: ${EL:-$PH}"; exit 1
  fi
  if [ "$A" = "1" ] && [ "${AGE:-0}" -gt $STALL ]; then
    [ "$last_state" != "stall" ] && echo "STALL: train.log unchanged ${AGE}s | ${STEP:-$PH}"; last_state=stall
  elif [ "$last_state" = "stall" ]; then echo "log moving again | ${STEP:-$PH}"; last_state=""
  fi
  tick=$((tick+1))
  if [ $((tick % 5)) -eq 1 ]; then  # heartbeat every 5 min, also when all is well
    if [ -n "$STEP" ]; then echo "status OK: training $STEP, checkpoints $CK"
    elif [ $started -eq 1 ]; then echo "status OK: preparing (model download / caching): ${PH:0:90}"
    elif [ -n "$SW" ]; then echo "status OK: stage 0 guidance sweep: $SW"
    else echo "status OK: installing dependencies"; fi
  fi
  sleep 60
done
