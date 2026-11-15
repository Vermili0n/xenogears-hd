#!/usr/bin/env bash
# 29.10 rebalance of the production render's end (user: yes). Waits until pod B's shards 1-3 are DONE, then:
#   splits shard 0's remaining v4 jobs (rebal_split.py): head -> pod A (restarted on prod_run_dd_head.sh, then its gears),
#   tail -> pod B's 3 GPUs (tail_run_b.sh, rebal_state running/done holds the watcher's final download);
# then watches the tail logs. Exits (= wakes Claude) when the switch is done or failed, and again is not needed after:
#   exit after "switched" - a second run with "watch" follows the tail until rebal_state = done or an error.
#   bash endgame.sh            wait + switch
#   bash endgame.sh watch      follow the tail
cd <XENO_SPRITES> || exit 1
LOG=pod/report/watch_ctl.log
SCR=tools   # 29.10: copied from the session scratchpad
O="-o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=no -i <HOME>/.ssh/<SSH_KEY>"
A() { ssh $O -p <POD_PORT> root@<POD_HOST> "$@" </dev/null; }
B() { ssh $O -p <POD_PORT> root@<POD_HOST> "$@" </dev/null; }
log() { echo "$(date '+%H:%M') REBAL: $*" | tee -a $LOG; }
fail() { log "FAILED: $*"; exit 1; }

if [ "$1" = watch ]; then
  while true; do
    st=$(B 'cat /workspace/rebal_state 2>/dev/null; cat /workspace/tail_*.log 2>/dev/null | tr "\r" "\n" | grep -acE "Traceback|out of memory|OutOfMemory|Killed"')
    [ -z "$st" ] && { sleep 180; continue; }
    state=$(echo "$st" | head -1); errs=$(echo "$st" | tail -1)
    [ "${errs:-0}" -gt 0 ] && fail "error lines in pod B tail logs ($errs)"
    [ "$state" = done ] && { log "pod B tail done"; exit 0; }
    sleep 180
  done
fi

until [ "$(B 'grep -h "PROD .* DONE" /workspace/prod_*.log 2>/dev/null' | wc -l)" -ge 3 ]; do sleep 180; done
log "pod B shards 1-3 done"
[ "$(A 'grep -c "PROD 0 DONE" /workspace/prod_0.log')" -ge 1 ] && { log "pod A already done - nothing to rebalance"; exit 0; }

A 'ls /workspace/res_prod/v4' > pod/report/a_v4.txt || fail "cannot list pod A"
read -r rest k tail < <(python $SCR/rebal_split.py pod/report/a_v4.txt) || fail "split"
[ -z "$tail" ] && fail "split gave nothing"
log "shard 0 remaining $rest v4 jobs: head $k -> pod A (+ gears), tail $tail -> pod B"
scp -q $O -P <POD_PORT> ai/prod/jobs_head0.json root@<POD_HOST>:/workspace/prod/ || fail "upload head"
scp -q $O -P <POD_PORT> pod/prod_run_dd_head.sh pod/check_recent.py root@<POD_HOST>:/workspace/ || fail "upload A scripts"
scp -q $O -P <POD_PORT> ai/prod/jobs_tail0.json root@<POD_HOST>:/workspace/prod/ || fail "upload tail"
scp -q $O -P <POD_PORT> pod/tail_run_b.sh root@<POD_HOST>:/workspace/ || fail "upload B script"
A 'cd /workspace && sed -i "s/\r$//" prod_run_dd_head.sh check_recent.py'
B 'cd /workspace && sed -i "s/\r$//" tail_run_b.sh'

# pod B tail first (the GPUs are free), then switch pod A to the head list
B 'cd /workspace && (setsid nohup bash tail_run_b.sh </dev/null >tail_run_b.out 2>&1 &)'   # subshell: ssh returns at once (29.10 it hung)
sleep 20
[ "$(B 'cat /workspace/rebal_state 2>/dev/null')" = running ] || fail "pod B tail did not start: $(B 'cat /workspace/tail_run_b.out')"
WR=$(A 'ps -eo pid,args' | awk '/[p]rod_run_dd.sh 0 4 0/{print $1}' | tr '\n' ' ')
RP=$(A 'ps -eo pid,args' | awk '/[i]nfer_pod.py .*--shard 0\/4/{print $1}' | head -1)
[ -z "$WR$RP" ] && fail "pod A wrapper/render pid not found (A finished meanwhile?) - tail runs anyway, check A"
A "kill -9 $WR 2>/dev/null; [ -n '$RP' ] && kill $RP; for i in \$(seq 30); do kill -0 $RP 2>/dev/null || break; sleep 2; done; \
   cd /workspace && python check_recent.py >> head_run.out 2>&1; (setsid nohup bash prod_run_dd_head.sh </dev/null >>head_run.out 2>&1 &)"
sleep 30
[ -n "$(A 'ps -eo pid,args' | awk '/[p]rod_run_dd_head/{print $1}')" ] || fail "pod A head run not running: $(A 'tail -5 /workspace/head_run.out')"
log "switched: pod A head $k + gears (killed wrapper $WR, render $RP), pod B tail $tail on 3 GPUs"
exit 0
