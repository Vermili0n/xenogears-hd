#!/bin/bash
cd /workspace/redraw/battle_story
T=1462
N=$(ls res/v4 2>/dev/null | wc -l)
L=$((T-N))
if grep -q RENDER_DONE infer.log 2>/dev/null; then ST=DONE
elif pgrep -f "[i]nfer_pod.py --jobs redraw/battle_story/jobs.json" >/dev/null; then ST=running
else ST=NOT_RUNNING; fi
echo "$N of $T done, $L left, about $((L*172/1000)) min, state: $ST"
