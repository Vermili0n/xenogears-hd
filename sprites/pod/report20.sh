#!/usr/bin/env bash
# One progress report line for the user: waits for the next :00/:20/:40 (unless "now"), then prints
#   Рендер: N из 36 964, ~R в час, ETA ~H ч.
# Rate = over the last ~hour of reports (history file); ETA = the slowest unfinished shard (its own eta from the log)
# plus ~0.25 h of gears for shards still on v4.
cd <XENO_SPRITES> || exit 1
TOTAL=36964
HIST=pod/report/.report20_hist
O="-o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=no -i <HOME>/.ssh/<SSH_KEY>"
Q='cd /workspace; echo "N $(find res_prod -name "*.png" | wc -l)"; for f in prod_*.log tail_*.log; do [ -f $f ] || continue; echo "S $f $(grep -acE "(PROD|TAIL) .* DONE" $f) $(tr "\r" "\n" < $f | grep -a "s/img eta" | tail -1)"; done'
if [ "$1" != now ]; then now=$(date +%s); sleep $(( (now / 1200 + 1) * 1200 - now )); fi
out="$(ssh $O -p <POD_PORT> root@<POD_HOST> "$Q" </dev/null 2>/dev/null)
$(ssh $O -p <POD_PORT> root@<POD_HOST> "$Q" </dev/null 2>/dev/null)"
now=$(date +%s)
n=$(echo "$out" | awk '$1=="N"{s+=$2} END{print s+0}')
eta=$(echo "$out" | awk '$1=="S" && $3==0 {for(i=4;i<=NF;i++) if($i=="eta"){e=$(i+1); sub("h","",e); e+=($4=="v4" && $2 ~ /^prod_/)?0.25:0; if(e>m)m=e}} END{printf "%.1f", m}')
echo "$now $n" >> $HIST; tail -12 $HIST > $HIST.tmp && mv $HIST.tmp $HIST
rate=$(awk -v now=$now -v n=$n '$1 >= now - 3700 && $1 <= now - 600 && !t {t=$1; c=$2} END{if(t && n>c) printf "%d", int((n-c)*3600/(now-t)/10+0.5)*10; else print "?"}' $HIST)
fmt() { echo "$1" | sed ':a;s/\B[0-9]\{3\}\>/ &/;ta'; }
echo "Рендер: $(fmt $n) из $(fmt $TOTAL), ~$rate в час, ETA ~${eta/./,} ч."
