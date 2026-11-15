#!/usr/bin/env bash
# Runs ON <JUMP_HOST>: submit every campaign job as a Gemini batch (Nano Banana 2.1, 4K). Key on stdin.
# Skips jobs that already have batches.json. Writes progress to /root/xeno_jobs/campaign_submit.log
KEY=$(cat)
cd /root/xeno_or
n=0
while IFS='|' read -r job prompt refs; do
  [ -z "$job" ] && continue
  d=/root/xeno_jobs/campaign/$job
  [ -f "$d/batches.json" ] && continue
  for try in 1 2 3; do
    if echo "$KEY" | python3 gem_batch.py submit --dir "$d" --refs "$d/in" --model gemini-nano-banana-2.1 --size 4K \
         --prompt-file "prompts/$prompt" --ref-list "$refs" --name "camp_$job" >> /root/xeno_jobs/campaign_submit.log 2>&1; then
      n=$((n+1)); break
    fi
    sleep 20
  done
done < /root/xeno_jobs/campaign_jobs.txt
echo "SUBMIT DONE $n" >> /root/xeno_jobs/campaign_submit.log
