#!/usr/bin/env bash
# Heartbeat for the user every 5 min (Monitor event stream): campaign build / submission / results + laptop progress.
cd <XENO_SPRITES>
source laptop/remote.sh
while true; do
  built=$(ls -d ai/campaign/*/in 2>/dev/null | wc -l)
  total=$(python -c "import json;print(len(json.load(open('ai/campaign/jobs.json'))))" 2>/dev/null || echo '?')
  sub=$(ssh -o ConnectTimeout=15 <JUMP_HOST> "ls /root/xeno_jobs/campaign/*/batches.json 2>/dev/null | wc -l" </dev/null 2>/dev/null)
  got=$(ssh -o ConnectTimeout=15 <JUMP_HOST> "ls /root/xeno_jobs/campaign/*/out/g*.png 2>/dev/null | wc -l" </dev/null 2>/dev/null)
  lap=$($LS "powershell -NoProfile -Command \"Get-Content C:\\xeno_sprites\\ai\\run_kleinfeilora.log -Tail 1\"" 2>/dev/null </dev/null | tr -d '\r')
  qa=$(ls ai/campaign/*/qa.json 2>/dev/null | wc -l)
  echo "$(date +%H:%M) проверено заданий: $qa/149 | сетки собраны: $built/$total заданий | отправлено пакетов: ${sub:-?} | получено картинок: $got | ноутбук: ${lap:-нет связи}"
  sleep 300
done
