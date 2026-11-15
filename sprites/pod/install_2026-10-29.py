"""29.10 evening: put every fix in place and build + install everything that is not in the pack yet (user: "нарезать и ставить").

  python pod/install_2026-10-29.py [--resume] [--workers N]   (RetroArch closed; log pod/report/install_2026-10-29.log)
--resume skips 1-2 (the fix list was applied by an interrupted run: its groups simply have no DONE and are built in 4).
1) the two hints that failed the test are replaced by their retries inside res_fix3:
   short_hair (m_7d47706ecb) <- res_retry_hair (twin's board); front (Fei) <- res_retry_s<seed> picked by the user;
2) tools/fix_apply.py res_fix3 (fix list; originals -> res_prod_prefix, groups rebuilt + installed, merge_shared);
3) tools/fix_apply.py res_regroup with regroup_map_8c2f0a / f4eb00 (--no-record): Krelian past board, Ramsus white;
4) prod_post --install for every complete group without DONE (heroes, massovka, gears), excluded groups left out;
5) merge_shared.py; summary.
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = r'<XENO_SPRITES>'
TOOLS = os.path.join(ROOT, 'tools')
sys.path.insert(0, TOOLS)
import prod_sync  # noqa: E402
from install_parts import excluded_groups  # noqa: E402

LOG = os.path.join(ROOT, 'pod', 'report', 'install_2026-10-29.log')
PRODR = os.path.join(ROOT, 'pod', 'report', 'prod')
FIX = os.path.join(PRODR, 'res_fix3', 'v4')


def log(*a):
    line = time.strftime('%H:%M ') + ' '.join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def run(cmd, tail=12):
    r = subprocess.run([sys.executable] + cmd, cwd=TOOLS, capture_output=True, text=True)
    for ln in r.stdout.strip().splitlines()[-tail:]:
        log('   ', ln)
    if r.returncode:
        log('    ERROR rc', r.returncode, r.stderr[-600:])
    return r.returncode


def main():
    if prod_sync.retroarch_running():
        sys.exit('RetroArch is running - close it first')
    resume = '--resume' in sys.argv   # steps 1-2 already done (fix renders copied, fix_done recorded, DONE removed)
    workers = sys.argv[sys.argv.index('--workers') + 1] if '--workers' in sys.argv else '8'
    log('=== start' + (' (resume: fix list already applied)' if resume else '') + f', workers {workers}')
    if not resume:
        fix_list()
    rest(workers)


def fix_list():
    # 1) retries in place of the failed hints
    n = 0
    for j in json.load(open(os.path.join(ROOT, 'ai', 'prod', 'jobs_retry_hair.json'))):
        src = os.path.join(PRODR, 'res_retry_hair', 'v4', j['name'] + '.png')
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(FIX, j['name'] + '.png'))
            n += 1
    for name, seed in json.load(open(os.path.join(PRODR, 'retry_front_pick.json'))).items():
        src = os.path.join(PRODR, f'res_retry_s{seed}', 'v4', name + '.png')
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(FIX, name + '.png'))
            n += 1
    log('retries copied into res_fix3:', n)
    # 2) fix list
    log('fix_apply res_fix3')
    run(['fix_apply.py', FIX])


def rest(workers):
    # 3) whole-group re-renders
    for m in ('regroup_map_8c2f0a.json', 'regroup_map_f4eb00.json'):
        log('fix_apply regroup', m)
        run(['fix_apply.py', os.path.join(PRODR, 'res_regroup', 'v4'), '--map', os.path.join(ROOT, 'ai', 'prod', m),
             '--no-record'])
    # 4) everything else
    prod_sync.fill_dups()
    ready, total, done = prod_sync.complete_groups()
    skip = excluded_groups()
    todo = [g for g in ready if g not in skip]
    log(f'groups: {done} done, {len(ready)} ready, {len(ready) - len(todo)} excluded -> building {len(todo)}')
    run(['prod_post.py', '--prod', os.path.join(ROOT, 'ai', 'prod'), '--res', os.path.join(PRODR, 'res_prod'),
         '--only', ','.join(todo), '--workers', workers, '--install'], tail=40)
    # 5) twins sharing pack files
    log('merge_shared')
    run(['merge_shared.py'], tail=2)
    ready2, total2, done2 = prod_sync.complete_groups()
    log(f'=== end: {done2} of {total2} groups DONE; not built: {[g for g in ready2 if g not in skip][:20]}')


if __name__ == '__main__':
    main()
