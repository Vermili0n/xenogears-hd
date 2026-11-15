"""Install of stage 3 by install_skip.json: battle sets with battle_rects.py, the dog with own_set.py. RetroArch closed."""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
skip = json.load(open(os.path.join(ROOT, 'ai', 'redraw', 'battle_rest', 'install_skip.json')))
for g, sk in skip.items():
    t = time.time()
    tail = ['--skip-frames', ','.join(map(str, sk))] if sk else []
    if g.startswith('o_'):
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'own_set.py'), 'install', g, g[2:]] + tail
    else:
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'battle_rects.py'), g[2:], g] + tail
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    out = (r.stdout.strip().splitlines() or [''])[-1]
    print(f'{g}: rc {r.returncode}, {time.time() - t:.0f} s, {out}' + (f' | ERR {r.stderr.strip()[-300:]}' if r.returncode else ''), flush=True)
print('INSTALL_DONE', flush=True)
