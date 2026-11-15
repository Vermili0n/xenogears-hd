#!/usr/bin/env bash
# Fei pilot, all field + scene sets from LoRA v3: download renders, compose, copy identical 39xx sets, slice
# everything together (texel-exact masks), preview, install. Run from the project root after run_pilot2.sh finished.
set -e
cd <XENO_SPRITES>
P="ssh -i $HOME/.ssh/<SSH_KEY> -p <POD_PORT> -o StrictHostKeyChecking=no root@<POD_HOST>"
$P 'cd /workspace && tar cf res_pilot2.tar res_pilot2'
scp -q -i ~/.ssh/<SSH_KEY> -P <POD_PORT> -o StrictHostKeyChecking=no root@<POD_HOST>:/workspace/res_pilot2.tar pod/report/pilot/
rm -rf pod/report/pilot/res_pilot2 && tar xf pod/report/pilot/res_pilot2.tar -C pod/report/pilot
echo "renders: $(ls pod/report/pilot/res_pilot2/v3 | wc -l)"
cd tools
python compose_set.py --render ../ai/render_pilot2 --res ../pod/report/pilot/res_pilot2/v3 --work ../ai/fei_pilotv3/work --offset-key fei
# 3933..3937 are byte-identical copies of 3922 (same frames, same parts)
for s in 3933 3934 3935 3936 3937; do
  for f in ../ai/fei_pilotv3/work/3922_0_*_red.png; do cp "$f" "${f/3922_0_/${s}_0_}"; done
done
ONLY=$(ls ../ai/fei_pilotv3/work | sed 's/_red.png//' | python -c "import sys; print(','.join(l.strip().rsplit('_',1)[0]+':'+str(int(l.strip().rsplit('_',1)[1])) for l in sys.stdin))")
rm -rf ../ai/fei_pilotv3/parts ../ai/fei_pilotv3/frames
python batch_redraw.py slice --heroes fei --out-tag _pilotv3 --exact-mask --ring 0 --only "$ONLY" | tail -1
for s in 2340_0 2442_0 2396_0 3922_0; do
  python preview_parts.py --hero-dir extracted/disc1_full/fei --parts ai/fei_pilotv3/parts --set $s --frames 0-15 --out pod/report/pilot_fei_$s.png --cols 8 --bg 150,170,90
done
python install_parts.py --parts ../ai/fei_pilotv3/parts | tail -1
echo PILOT FINISHED
