Re-render eyepatch: 33 frames (45 with twins) + head close-ups -> 66 jobs, about 16 min on one L40S.
Seed 7, hint: "he wears a large black eyepatch, the dark shape on his face in the pixel sprite IS the eyepatch: draw it at exactly that place and size, it fully covers one eye, the strap goes around his head; only one eye is covered and the other eye stays open; not just a thin headband on the forehead, not goggles, not a visor, not sunglasses"

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
   scp -P PORT -r ai\redraw\eyepatch root@HOST:/workspace/redraw/
   THREE seeds (7, 11, 23) in one run (run.sh), about 50 min on one L40S:
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/eyepatch/run.sh > redraw/eyepatch/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/eyepatch/infer.log; ls /workspace/redraw/eyepatch/res_*/v4 | grep -c png"
   (done: RENDER_DONE and 198 files, 66 per seed)

3. Download, then stop the pod in RunPod:
   scp -P PORT -r root@HOST:/workspace/redraw/eyepatch/res_* ai\redraw\eyepatch\

4. Tell Claude. It picks the best seed of every frame by eye and installs only these frames.
   Do NOT run fix_apply.py on this folder: it rebuilds the whole h_bart group and would undo the 01.11 fix of the
   back views (frames 140, 141, 147, 157, 163).
