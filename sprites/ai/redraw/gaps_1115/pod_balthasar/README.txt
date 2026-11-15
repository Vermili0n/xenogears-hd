Balthasar (portrait 562) field set 48c502a64f again, without the moustache: 76 frames + 48 heads, x2 boards (A: old board + portrait face, B: official art + portrait) = 248 pictures, seed 42, LoRA v4.
Pod: as pod_multitex\README.txt step 1; upload this folder to /workspace/redraw/pod_balthasar, then
   ssh -J <JUMP_HOST> -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/pod_balthasar/run.sh > redraw/pod_balthasar/infer.log 2>&1 &)"
(done: RENDER_DONE and 248 files in res_42/v4). Download res_42.
Install: the user picks board A or B on the sheets; compose (heads 16x) + slice + project like the production
(prod_post for this group with the picked results) - an overwrite of the set's files: the user's word first.

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
