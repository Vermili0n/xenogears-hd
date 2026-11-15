#!/usr/bin/env bash
# One progress line of the 29.10 install chain (pod/install_2026-10-29.py) for the user: waits for the next :00/:20/:40
# (unless "now"), prints  Установка: N из M групп, ~R в час, ETA ~H ч (этап: ...).  M = 592 groups minus excluded ones.
cd <XENO_SPRITES> || exit 1
LOG=pod/report/install_2026-10-29.log
HIST=pod/report/.install_hist
if [ "$1" != now ]; then now=$(date +%s); sleep $(( (now / 1200 + 1) * 1200 - now )); fi
now=$(date +%s)
done_n=$(ls ai/prod_work/*/DONE 2>/dev/null | wc -l)
excl=$(grep -c '^group:' ai/prod/exclude_parts.txt)
total=$(( 592 - excl ))
stage=$(grep -E "fix_apply|groups:|merge_shared|=== end" $LOG | tail -1 | cut -c7-80)
echo "$now $done_n" >> $HIST; tail -12 $HIST > $HIST.tmp && mv $HIST.tmp $HIST
rate=$(awk -v now=$now -v n=$done_n '$1 >= now - 3700 && $1 <= now - 600 && !t {t=$1; c=$2} END{if(t && n>c) printf "%d", (n-c)*3600/(now-t); else print "?"}' $HIST)
eta="?"; [ "$rate" != "?" ] && [ "$rate" -gt 0 ] && eta=$(awk -v r=$rate -v n=$done_n -v t=$total 'BEGIN{printf "%.1f", (t-n)/r}' | tr . ,)
if grep -q "=== end" $LOG; then
  echo "Установка завершена: $done_n из $total групп. $(grep '=== end' $LOG | tail -1 | cut -c7-200)"
else
  echo "Установка: $done_n из $total групп, ~$rate в час, ETA ~$eta ч (этап: $stage)"
fi
