Remaining 15.11 gaps that need drawings: 76 pictures, about 8 min of an RTX PRO 6000 / L40S
(5.7-6.6 s a picture, 12.11) + ~10 min setup; both LoRAs on one pod (v4 = characters, v2 = gears).
roni46: 6 pictures (LoRA v4)
f2427: 26 pictures (LoRA v4)
f3837: 9 pictures (LoRA v4)
gear456: 10 pictures (LoRA v2)
f2410: 25 pictures (LoRA v2)

Pod: as ai\redraw\gaps_1115\pod_multitex\README.txt step 1 (setup_infer.sh, infer_pod.py), plus BOTH LoRAs:
   scp -J <JUMP_HOST> -P PORT lora\klein_v4\xeno_klein_v4.safetensors lora\klein_v2\xeno_klein_v2.safetensors root@HOST:/workspace/lora/
Upload the folder (tar through <JUMP_HOST>) to /workspace/redraw/pod_rest, then
   ssh -J <JUMP_HOST> -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/pod_rest/run.sh > redraw/pod_rest/infer.log 2>&1 &)"
Download res_* (tar through <JUMP_HOST>), stop the pod, tell Claude.

Install (separate work, after the user's look at the sheets):
  roni46: pick a seed by eye; slice ONLY the head piece r0x07y5aw0dh0d into the HD sheet 86ef69b7-98d6171a (and the other
    uploads/rects of set 44f27d4ef0 that hold texels 7..19 x 90..102) - an OVERWRITE of existing files: user's word first.
  gear456: like zero_block/install.py (HeroZ, compose + slice, h-1 aliases as gear_redraw install), only the 65 missing names.
  f2410 / f2427 / f3837: compose + slice by their own layouts (streamed\f*), as id_chi/retarget stage_parts; new names only.

=== 16.11: what was run on the pod (<POD_HOST>:<POD_PORT>, RTX PRO 6000, key ~/.ssh/<SSH_KEY> through -J <JUMP_HOST>) ===
P="-o BatchMode=yes -J <JUMP_HOST> -i ~/.ssh/<SSH_KEY>"   (Git Bash; PowerShell: the same flags)
ssh $P -p PORT root@HOST "mkdir -p /workspace/lora /workspace/redraw"
scp $P -P PORT pod/setup_infer.sh pod/infer_pod.py root@HOST:/workspace/
ssh $P -p PORT root@HOST "cd /workspace && (setsid nohup bash setup_infer.sh > setup_infer.log 2>&1 &)"    -> SETUP_OK
scp $P -P PORT lora/klein_v4/xeno_klein_v4.safetensors lora/klein_v2/xeno_klein_v2.safetensors root@HOST:/workspace/lora/
tar -cf - pod_multitex pod_rest | ssh $P -p PORT root@HOST "cd /workspace/redraw && tar --no-same-owner -xf -"   (from gaps_1115)
redraw/run_both.sh = pod_multitex/run.sh then pod_rest/run.sh (BOTH_DONE in redraw/run_both.log);
redraw/run_balth_after.sh waits for BOTH_DONE, then pod_balthasar/run.sh (BALTH_DONE).
Download: ssh $P -p PORT root@HOST "cd /workspace/redraw/<job> && tar -cf - res_*" | tar -xf -   (in gaps_1115\<job>)
Check before install: python check_jobs.py <job>; count the PNGs (552 / 76 / 248).

=== Install (local, one process; nothing is overwritten) ===
python ai\redraw\gaps_1115\install_pod.py multitex            stage + new.txt / overwrite.txt + preview_<group>.png
python ai\redraw\gaps_1115\install_pod.py rest --roni-seed N  (N = the seed picked by eye: 7, 11 or 23)
python ai\redraw\gaps_1115\install_pod.py balthasar --board a|b
Look at the previews, then the same command with --install: ONLY the names in new.txt go into both packs
(log inst_<job>\installed.txt). Names in overwrite.txt (an old drawing in the pack) wait for the user's word and a
backup (as pink_install.py does).
