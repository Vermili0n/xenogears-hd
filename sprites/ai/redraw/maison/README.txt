Re-render maison: 71 frames (220 with twins) + head close-ups -> 142 jobs, about 35 min on one L40S.
Seed 7, hint: "he is clean-shaven: no mustache and no beard, a bare upper lip; thick white eyebrows and small round glasses"

Pod (HOST / PORT from RunPod "Connect -> SSH over exposed TCP"; key ~/.ssh/<SSH_KEY> or ~/.ssh/<SSH_KEY>).
Run from the xeno_sprites folder in PowerShell.

1. A fresh pod only (skip when setup_infer.log already ends with SETUP_OK):
   scp -P PORT pod\setup_infer.sh pod\infer_pod.py root@HOST:/workspace/
   ssh -p PORT root@HOST "mkdir -p /workspace/lora /workspace/redraw"
   scp -P PORT lora\klein_v4\xeno_klein_v4.safetensors root@HOST:/workspace/lora/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup bash setup_infer.sh > setup_infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/setup_infer.log"        (repeat until SETUP_OK, ~10 min)

2. Upload and render:
   ssh -p PORT root@HOST "mkdir -p /workspace/redraw"
   scp -P PORT -r ai\redraw\maison root@HOST:/workspace/redraw/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup sh -c 'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/maison/jobs.json --out redraw/maison/res --crop --cfg 4 --seed 7 --lora lora/xeno_klein_v4.safetensors; echo RENDER_DONE' > redraw/maison/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/maison/infer.log; ls /workspace/redraw/maison/res/v4 | wc -l"
   (done: RENDER_DONE and 142 files)

3. Download, then stop the pod in RunPod:
   scp -P PORT -r root@HOST:/workspace/redraw/maison/res ai\redraw\maison\

4. Look at the renders by eye: ai\redraw\maison\res\v4\*.png (compare with ai\redraw\maison\before\)

5. Install (RetroArch closed):
   python tools\fix_apply.py ai\redraw\maison\res\v4 --map ai\redraw\maison\map.json --no-record
   python tools\redraw_finish.py
   Check in game. Previews of the sliced frames: ai\prod_work\<group>\frames\

Undo (RetroArch closed):
   python tools\fix_apply.py ai\redraw\maison\before --map ai\redraw\maison\undo_map.json --no-record
   python tools\redraw_finish.py
