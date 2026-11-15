#!/usr/bin/env bash
# Runs ON <JUMP_HOST> in the foreground (key on stdin): poll every submitted campaign batch until all are finished.
KEY=$(cat)
cd /root/xeno_or
while true; do
  pending=0
  for d in /root/xeno_jobs/campaign/*/; do
    [ -f "$d/batches.json" ] || continue
    if grep -q '"done"' "$d/batches.json" && ! grep -q -v -e '"done"' <(python3 -c "import json;print('\n'.join('done' if b.get('done') else 'open' for b in json.load(open('$d/batches.json'))))"); then
      continue
    fi
    echo "$KEY" | python3 gem_batch.py poll --dir "$d" > /dev/null 2>&1
    python3 -c "import json,sys;sys.exit(0 if all(b.get('done') for b in json.load(open('$d/batches.json'))) else 1)" || pending=$((pending+1))
  done
  submitted=$(ls /root/xeno_jobs/campaign/*/batches.json 2>/dev/null | wc -l)
  echo "$(date +%H:%M) poll: submitted $submitted, still running $pending" >> /root/xeno_jobs/campaign_poll.log
  if grep -q "SUBMIT DONE" /root/xeno_jobs/campaign_submit.log 2>/dev/null && [ "$pending" -eq 0 ]; then
    echo "POLL DONE" >> /root/xeno_jobs/campaign_poll.log
    break
  fi
  sleep 120
done
