#!/usr/bin/env bash
# Wait until all 4 render shards are finished (PROD <i> DONE in the logs), then download the renders that are not
# here yet from both pods into pod/report/prod/res_prod (v4/, v2/). Download only: no assembly, nothing installed.
#   bash download_when_done.sh        wait for the end of the render, then download
#   bash download_when_done.sh now    download what is ready right now
cd <XENO_SPRITES> || exit 1
KEY=~/.ssh/<SSH_KEY>
O="-o ConnectTimeout=25 -o BatchMode=yes -o StrictHostKeyChecking=no"
done_on() { ssh $O -p "$1" -i "$KEY" "root@$2" 'grep -h "PROD .* DONE" /workspace/prod_*.log 2>/dev/null' </dev/null | wc -l; }
if [ "$1" != "now" ]; then
  until [ "$(done_on <POD_PORT> <POD_HOST>)" -ge 1 ] && [ "$(done_on <POD_PORT> <POD_HOST>)" -ge 3 ]; do
    echo "$(date '+%H:%M') render not finished yet, next check in 10 min"
    sleep 600
  done
  echo "$(date '+%H:%M') all 4 shards done"
fi
python -c "import sys; sys.path.insert(0, 'tools'); import prod_sync; prod_sync.pull()"
echo "$(date '+%H:%M') download finished (if a line says N incomplete > 0, run again with: now)"
