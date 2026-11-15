#!/usr/bin/env bash
# Pilot 3 (v4): download renders, compose each set twice (with / without the 16x head pass), slice at 8x with the
# game UV compensation, GAME_UV previews, install the variant given as $1 (head|nohead, default head).
set -e
cd <XENO_SPRITES>
VARIANT=${1:-head}
RES=pod/report/pilot3/res_pilot3/v4
SSHO="-o ProxyJump=<JUMP_HOST> -i $HOME/.ssh/<SSH_KEY> -o StrictHostKeyChecking=no"
if [ ! -f pod/report/pilot3/.downloaded ]; then
  mkdir -p pod/report/pilot3
  ssh $SSHO -p <POD_PORT> root@<POD_HOST> 'cd /workspace && tar -cf - res_pilot3' | tar -xf - --no-same-owner -C pod/report/pilot3
  touch pod/report/pilot3/.downloaded
fi
echo "renders: $(ls $RES | wc -l)"
# name | sprite folder | colour offset key
SETS="alice|extracted/npc_full/3d2b1c1562|c_alice_3d2b1c
timothy|extracted/npc_full/d8943ce397|c_timothy_d8943c
npc36e3|extracted/npc_full/36e3637a9a|m_36e3637a9a
npcf6ad|extracted/npc_full/f6ad8ce563|m_f6ad8ce563
fei|extracted/disc1_full/fei|fei"
cd tools
echo "$SETS" | while IFS='|' read -r name hd off; do
  for v in head nohead; do
    tag=p3${v:0:1}_$name                       # p3h_<name> / p3n_<name>
    W=../ai/$tag/work
    rm -rf ../ai/$tag && mkdir -p $W
    python compose_set.py --render ../ai/render_pilot3 --res ../$RES --work $W --name $name --offset-key $off --out-scale 8 \
      $([ $v = nohead ] && echo --no-head) | tail -1
    ONLY=$(ls $W | grep _red.png | sed 's/_red.png//' | python -c "import sys; print(','.join(l.strip().rsplit('_',1)[0]+':'+str(int(l.strip().rsplit('_',1)[1])) for l in sys.stdin))")
    python batch_redraw.py slice --heroes $tag --hero-dir ../$hd --scale 8 --exact-mask --ring 0 --uv-compensate --only "$ONLY" | tail -1
  done
done
cd ..
echo "PILOT3 POST DONE (install with: python tools/install_parts.py --parts ai/p3h_<name>/parts for each set)"
