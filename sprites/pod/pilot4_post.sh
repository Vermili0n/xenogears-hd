#!/usr/bin/env bash
# Pilot 4: Fei battle sets 2988_0 + 3005_0 (part-cover frames). Download, compose (head pass), slice at 8x with the
# game UV compensation, install ONLY parts that pilot 3 (set 2709_3) did not install - shared parts stay as seen.
set -e
cd <XENO_SPRITES>
export OPENBLAS_NUM_THREADS=1
# renders were fetched through <JUMP_HOST> (the direct pod link is throttled); fei__2988_0_058.png was lost (truncated)
echo "renders: $(ls pod/report/pilot4/res_pilot4/v4 | wc -l)"
cd tools
W=../ai/p4h_fei/work
rm -rf ../ai/p4h_fei && mkdir -p $W
python compose_set.py --render ../ai/render_pilot4 --res ../pod/report/pilot4/res_pilot4/v4 --work $W --name fei --offset-key fei --out-scale 8 | tail -1
ONLY=$(ls $W | grep _red.png | sed 's/_red.png//' | python -c "import sys; print(','.join(l.strip().rsplit('_',1)[0]+':'+str(int(l.strip().rsplit('_',1)[1])) for l in sys.stdin))")
python batch_redraw.py slice --heroes p4h_fei --hero-dir ../extracted/disc1_full/fei --scale 8 --exact-mask --ring 0 --uv-compensate --only "$ONLY" | tail -1
cd ..
mkdir -p ai/p4h_fei/parts_new
for f in ai/p4h_fei/parts/*.png; do b=$(basename $f); [ -f ai/p3h_fei/parts/$b ] || cp $f ai/p4h_fei/parts_new/; done
echo "new parts: $(ls ai/p4h_fei/parts_new | wc -l) of $(ls ai/p4h_fei/parts | wc -l)"
echo PILOT4 POST DONE
