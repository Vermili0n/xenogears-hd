"""Time series of HD VRAM from a RetroArch log: live HD images (all) vs the GPU cache's own entries / MB.
The gap (live - cache - fused) is HD memory nobody budgets.  python vram_series.py <log> [every]"""
import re
import sys

every = int(sys.argv[2]) if len(sys.argv) > 2 else 20
alloc = re.compile(r'alloc: (\d+) MiB total.*live: (\d+) images (\d+) MiB \(HD (\d+) / (\d+) MiB\)')
mode = re.compile(r'vram (\d+)/(\d+) MB \((\d+) entries\)')
fused = re.compile(r'fused: (\d+) pages, ([\d.]+) MiB')
oom = re.compile(r'out of VRAM')
cur = {}
rows = []
n_oom = 0
for line in open(sys.argv[1], encoding='utf-8', errors='replace'):
    if oom.search(line):
        n_oom += 1
    m = alloc.search(line)
    if m:
        cur.update(total=int(m[1]), hd_n=int(m[4]), hd_mb=int(m[5]))
        continue
    m = mode.search(line)
    if m:
        cur.update(c_mb=int(m[1]), c_n=int(m[3]))
        continue
    m = fused.search(line)
    if m and 'hd_n' in cur and 'c_n' in cur:
        cur.update(f_n=int(m[1]), f_mb=float(m[2]), oom=n_oom)
        rows.append(dict(cur))
print(f'{"#":>4} {"alloc":>6} {"HD n":>6} {"HD MB":>6} {"cacheN":>6} {"cacheMB":>7} {"fusedN":>6} {"gap n":>6} {"gap MB":>7} oom')
for i, r in enumerate(rows):
    if i % every == 0 or i == len(rows) - 1:
        gn = r['hd_n'] - r['c_n'] - r['f_n']
        gm = r['hd_mb'] - r['c_mb'] - r['f_mb']
        print(f'{i:>4} {r["total"]:>6} {r["hd_n"]:>6} {r["hd_mb"]:>6} {r["c_n"]:>6} {r["c_mb"]:>7} {r["f_n"]:>6} {gn:>6} {gm:>7.0f} {r["oom"]}')
