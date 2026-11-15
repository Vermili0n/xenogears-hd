"""Split shard 0's remaining v4 jobs between pod A (head, 1 GPU, then its 111 gears) and pod B (tail, 3 GPUs) so both
finish about together.   python rebal_split.py <file with pod A's res_prod/v4 names>
Writes ai/prod/jobs_head0.json and jobs_tail0.json; prints remaining, head, tail."""
import json
import os
import sys

ROOT = r'<XENO_SPRITES>'
PROD = os.path.join(ROOT, 'ai', 'prod')
SA, SB = 8.5, 7.7            # s/img on pod A and per GPU on pod B (29.10 logs)

have = {ln.strip()[:-4] for ln in open(sys.argv[1]) if ln.strip().endswith('.png')}
shard0 = json.load(open(os.path.join(PROD, 'jobs_v4_dd.json')))[0::4]
gears = len(json.load(open(os.path.join(PROD, 'jobs_v2_dd.json')))[0::4])
rest = [j for j in shard0 if j['name'] not in have]
# A: k * SA + gears * SA = B: (len(rest) - k) / 3 * SB
k = max(0, round((len(rest) * SB / 3 - gears * SA) / (SA + SB / 3)))
json.dump(rest[:k], open(os.path.join(PROD, 'jobs_head0.json'), 'w'), indent=1)
json.dump(rest[k:], open(os.path.join(PROD, 'jobs_tail0.json'), 'w'), indent=1)
print(len(rest), k, len(rest) - k)
