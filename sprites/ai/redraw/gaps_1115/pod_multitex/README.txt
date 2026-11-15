Map NPC sets cut from the wrong texture, rendered again from the fixed cut (npc_fixed.py):
9 sets, 475 frames + 77 head close-ups = 552 pictures (seed 42), about 59 min on one RTX PRO 6000 / L40S
(5.7-6.6 s a picture measured 12.11) plus ~10 min pod setup.

Sets: 1ecec3878b (m_1ecec3878b), 2a6c20d32b (m_2a6c20d32b), 507b56107a (m_507b56107a), 85dbb0f247 (c_gaspar_uzuki_85dbb0), 9b2c042653 (m_9b2c042653), a00b6f391b (m_a00b6f391b), b1289f4abd (m_b1289f4abd), c2df43a7cd (c_kelvena_c2df43), c3531d4e57 (m_c3531d4e57)

Board check BEFORE the pod: the campaign boards of these groups were drawn from the same garbled frames
(boards\npc_1ecec3878b.png: Khan with misplaced pieces). Colours and face are usable; if the user wants a clean board,
one Nano Banana grid of 16 fixed frames per set (Google batch ~$0.06-0.12 each) comes first.

Pod (HOST / PORT from RunPod "Connect -> SSH over exposed TCP"; key ~/.ssh/<SSH_KEY>; all transfers through -J <JUMP_HOST>).
Run from the xeno_sprites folder in PowerShell.
1. A fresh pod only (skip when setup_infer.log already ends with SETUP_OK):
   scp -J <JUMP_HOST> -P PORT pod\setup_infer.sh pod\infer_pod.py root@HOST:/workspace/
   ssh -J <JUMP_HOST> -p PORT root@HOST "mkdir -p /workspace/lora /workspace/redraw"
   scp -J <JUMP_HOST> -P PORT lora\klein_v4\xeno_klein_v4.safetensors root@HOST:/workspace/lora/
   ssh -J <JUMP_HOST> -p PORT root@HOST "cd /workspace && (setsid nohup bash setup_infer.sh > setup_infer.log 2>&1 &)"
   ssh -J <JUMP_HOST> -p PORT root@HOST "tail -2 /workspace/setup_infer.log"        (until SETUP_OK, ~10 min)
2. Upload and render:
   tar the folder ai\redraw\gaps_1115\pod_multitex, copy it to /workspace/redraw/pod_multitex (through <JUMP_HOST>), then
   ssh -J <JUMP_HOST> -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/pod_multitex/run.sh > redraw/pod_multitex/infer.log 2>&1 &)"
   (done: RENDER_DONE and 552 files in res_42/v4)
3. Download res_42 (tar through <JUMP_HOST>), stop the pod.
4. Install = new work: compose/slice per set from fixed\<set> (Hero folders, parts r<tid>x..), then a projection that
   writes texture k's HD into the upload of image k of the item (npc_maps.cmd_project knows only image 0), BC7, seam fill.
   The c_gaspar / c_kelvena / m_507b56107a / m_81c7c75ab9 groups are already in the pack (drawn from the garbled cut):
   replacing them is an overwrite - only with the user's word.

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

Per set, only the new names (sets not drawn before; nothing overwritten, no redo):
python ai\redraw\gaps_1115\install_pod.py multitex --install-only --sets 1ecec3878b,2a6c20d32b,a00b6f391b,b1289f4abd,c3531d4e57
(c_gaspar_uzuki_85dbb0, c_kelvena_c2df43, m_507b56107a, m_9b2c042653 have files in the pack from the garbled cut:
overwrite.txt - with the user's word and a backup only.)
