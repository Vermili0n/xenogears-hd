#!/usr/bin/env bash
# Render watcher for Claude: checks both pods every 5 min, writes progress to pod/report/watch_ctl.log every 30 min,
# downloads finished renders every 2 h (prod_sync.pull, download only). Exits (= wakes Claude) on:
#   new error lines in a log, a shard wrapper gone without its DONE marker (2 checks), a shard with no progress for 30 min,
#   a pod unreachable for 15 min, or all 4 shards DONE (then a final download first).
cd <XENO_SPRITES> || exit 1
LOG=pod/report/watch_ctl.log
O="-o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=no -i <HOME>/.ssh/<SSH_KEY>"
Q=$(cat <<'EOF'
cd /workspace
for f in prod_*.log; do i=${f#prod_}; i=${i%.log}
  last=$(tr "\r" "\n" < $f | grep -a "s/img eta" | tail -1)
  d=$(grep -ac "PROD .* DONE" $f)
  e=$(tr "\r" "\n" < $f | grep -acE "Traceback|out of memory|OutOfMemory|Killed|Error")
  echo "S|$i|$d|$e|$last"
done
echo "N|$(find res_prod -name '*.png' | wc -l)|$(pgrep -f '[p]rod_run_dd' | wc -l)|$(pgrep -f '[i]nfer_pod' | wc -l)"
echo "X|$(cat rebal_state 2>/dev/null)"
EOF
)
pull() { python -c "import sys; sys.path.insert(0, 'tools'); import prod_sync; prod_sync.pull()" 2>&1 | tail -3 | sed "s/^/$(date '+%H:%M') /" >> $LOG; }
event() { echo "$(date '+%H:%M') EVENT: $*" | tee -a $LOG; exit 0; }
SCR=tools   # 29.10: copied from the session scratchpad
# back-view QA of newly complete groups (qa_auto.py) runs in the background so pod checks go on meanwhile;
# qa_check (every loop) wakes Claude when a finished run left sheets to look at
QAOUT=pod/report/qa/auto/qa_run.out; QAPID=""
qa_start() { if [ -n "$QAPID" ] && kill -0 "$QAPID" 2>/dev/null; then return; fi
  python tools/qa_auto.py > $QAOUT 2>&1 & QAPID=$!; }
qa_check() {
  [ -z "$QAPID" ] && return; kill -0 "$QAPID" 2>/dev/null && return
  local rc n head; wait "$QAPID"; rc=$?; QAPID=""; head=$(head -1 $QAOUT)
  echo "$(date '+%H:%M') $head" >> $LOG
  [ $rc -ne 0 ] && event "QA failed: $(tail -3 $QAOUT | tr '\n' ' ')"
  n=$(echo "$head" | sed -n 's/.*, \([0-9]*\) sheets to review.*/\1/p')
  [ "${n:-0}" -gt 0 ] && event "$head"
}

declare -A base_err last_line still miss gone
lastlog=0; lastpull=0
echo "$(date '+%H:%M') watcher started" >> $LOG
while true; do
  now=$(date +%s); alldone=0; total=0; summary=""; rebal=""
  for pod in "A <POD_PORT> <POD_HOST>" "B <POD_PORT> <POD_HOST>"; do
    set -- $pod; name=$1
    out=$(ssh $O -p $2 root@$3 "$Q" 2>/dev/null </dev/null)
    if [ -z "$out" ]; then
      miss[$name]=$(( ${miss[$name]:-0} + 1 ))
      [ ${miss[$name]} -ge 3 ] && event "pod $name unreachable for 15 min"
      summary+=" $name:unreachable"; continue
    fi
    miss[$name]=0; ndone=0; nshards=0; wrappers=""
    while IFS='|' read -r tag i d e last; do
      if [ "$tag" = N ]; then
        total=$(( total + i )); wrappers=$d
        continue
      fi
      if [ "$tag" = X ]; then   # pod B renders shard 0's tail after the rebalance (endgame.sh): not done until "done"
        [ "$i" = running ] && { rebal=1; summary+=" B:tail running"; }
        continue
      fi
      nshards=$(( nshards + 1 )); [ "$d" -ge 1 ] && ndone=$(( ndone + 1 ))
      [ -z "${base_err[$i]}" ] && base_err[$i]=$e
      [ "$e" -gt "${base_err[$i]}" ] && event "shard $i: new error lines in prod_$i.log ($e, was ${base_err[$i]})"
      if [ "$d" -lt 1 ]; then
        if [ "$last" = "${last_line[$i]}" ]; then still[$i]=$(( ${still[$i]:-0} + 1 )); else still[$i]=0; last_line[$i]=$last; fi
        [ ${still[$i]} -ge 6 ] && event "shard $i: no progress for 30 min (last: $last)"
      fi
      summary+=" s$i:${last% *s/img*}$( [ "$d" -ge 1 ] && echo ' DONE')"
      eta=$(echo "$last" | sed -n 's/.*eta \([0-9.]*\)h.*/\1/p')
      [ -n "$eta" ] && [ "$d" -lt 1 ] && summary+="(~$(date -d "+$(awk "BEGIN{print int($eta*60)}") minutes" '+%H:%M'))"
    done <<< "$out"
    if [ $(( nshards - ndone )) -gt "${wrappers:-0}" ]; then
      gone[$name]=$(( ${gone[$name]:-0} + 1 ))
      [ ${gone[$name]} -ge 2 ] && event "pod $name: $((nshards - ndone)) shards not done but only ${wrappers:-0} wrappers alive"
    else gone[$name]=0; fi
    [ $ndone -eq $nshards ] && alldone=$(( alldone + 1 ))
  done
  if [ $alldone -eq 2 ] && [ -z "$rebal" ]; then
    [ -n "$QAPID" ] && wait "$QAPID"; QAPID=""
    pull; pull; python tools/qa_auto.py > $QAOUT 2>&1; echo "$(date '+%H:%M') $(head -1 $QAOUT)" >> $LOG
    event "ALL 4 SHARDS DONE, $total images on pods; downloaded; $(head -1 $QAOUT) (see $LOG)"
  fi
  if [ $(( now - lastlog )) -ge 1800 ]; then echo "$(date '+%H:%M') $total/36964 |$summary" >> $LOG; lastlog=$now; fi
  if [ $(( now - lastpull )) -ge 7200 ] && [ -z "$QAPID" ]; then pull; lastpull=$now; qa_start; fi
  qa_check
  [ -n "$ONCE" ] && { echo "$total |$summary"; exit 0; }
  sleep 300
done
