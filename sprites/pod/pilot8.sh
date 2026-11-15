#!/usr/bin/env bash
# Fei pilot at 8x (fused-page mip blur workaround): compose all renders at 8x, slice at 8x, preview, install.
set -e
cd <XENO_SPRITES>/tools
W=../ai/fei_pilot8/work
rm -rf ../ai/fei_pilot8 && mkdir -p $W
python compose_set.py --render ../ai/render_pilot --res ../pod/report/pilot/res_pilot/v3 --work $W --offset-key fei --out-scale 8
python compose_set.py --render ../ai/render_pilot2 --res ../pod/report/pilot/res_pilot2/v3 --work $W --offset-key fei --out-scale 8
for s in 3933 3934 3935 3936 3937; do
  for f in $W/3922_0_*_red.png; do cp "$f" "${f/3922_0_/${s}_0_}"; done
done
ONLY=$(ls $W | sed 's/_red.png//' | python -c "import sys; print(','.join(l.strip().rsplit('_',1)[0]+':'+str(int(l.strip().rsplit('_',1)[1])) for l in sys.stdin))")
python batch_redraw.py slice --heroes fei --out-tag _pilot8 --scale 8 --exact-mask --ring 0 --uv-compensate --only "$ONLY" | tail -1
GAME_UV=1 python preview_parts.py --hero-dir extracted/disc1_full/fei --parts ai/fei_pilot8/parts --set 427_0 --frames 184-199 --out pod/report/pilot8_idle.png --cols 8 --bg 150,170,90
python install_parts.py --parts ../ai/fei_pilot8/parts | tail -1
echo PILOT8 DONE
