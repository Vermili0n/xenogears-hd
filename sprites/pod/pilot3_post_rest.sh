#!/usr/bin/env bash
# Finish pilot 3 post-processing for the sets not done yet (same steps as pilot3_post.sh).
cd <XENO_SPRITES>/tools
export OPENBLAS_NUM_THREADS=1
RES=../pod/report/pilot3/res_pilot3/v4
run() {  # name hero_dir offset variant
  name=$1; hd=$2; off=$3; v=$4; tag=p3${v:0:1}_$name; W=../ai/$tag/work
  rm -rf ../ai/$tag && mkdir -p $W
  python compose_set.py --render ../ai/render_pilot3 --res $RES --work $W --name $name --offset-key $off --out-scale 8 \
    $([ $v = nohead ] && echo --no-head) 2>&1 | tail -1
  ONLY=$(ls $W | grep _red.png | sed 's/_red.png//' | python -c "import sys; print(','.join(l.strip().rsplit('_',1)[0]+':'+str(int(l.strip().rsplit('_',1)[1])) for l in sys.stdin))")
  python batch_redraw.py slice --heroes $tag --hero-dir ../$hd --scale 8 --exact-mask --ring 0 --uv-compensate --only "$ONLY" 2>&1 | tail -1
}
run npc36e3 extracted/npc_full/36e3637a9a m_36e3637a9a nohead
run npcf6ad extracted/npc_full/f6ad8ce563 m_f6ad8ce563 head
run npcf6ad extracted/npc_full/f6ad8ce563 m_f6ad8ce563 nohead
run fei extracted/disc1_full/fei fei head
run fei extracted/disc1_full/fei fei nohead
echo POST REST DONE
