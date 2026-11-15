#!/usr/bin/env bash
# Night heartbeat (every 10 min): LoRA v2 dataset build + laptop Fei redraw.
cd <XENO_SPRITES>
source laptop/remote.sh
while true; do
  pairs=$(ls ai/pairs_v2/target/*.png 2>/dev/null | wc -l)
  lap=$($LS "powershell -NoProfile -Command \"Get-Content C:\xeno_sprites\ai\run_kleinfeilora.log -Tail 1\"" 2>/dev/null </dev/null | tr -d '\r')
  echo "$(date +%H:%M) обучающий набор: $pairs троек | ноутбук: ${lap:-нет связи}"
  sleep 600
done
