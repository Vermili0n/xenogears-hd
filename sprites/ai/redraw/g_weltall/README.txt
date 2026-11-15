Field gear g_weltall: 63 frames (part cover of 78), about 15 min on one L40S. LoRA v2, seed 42.

Pod (HOST / PORT from RunPod; run from the xeno_sprites folder in PowerShell). A fresh pod: setup as in
КАК_ПЕРЕРИСОВАТЬ.md step 3.1, plus the gear LoRA:
   scp -P PORT lora\klein_v2\xeno_klein_v2.safetensors root@HOST:/workspace/lora/

Upload and render:
   ssh -p PORT root@HOST "mkdir -p /workspace/redraw"
   scp -P PORT -r ai\redraw\g_weltall root@HOST:/workspace/redraw/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup sh -c 'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/g_weltall/jobs.json --out redraw/g_weltall/res --crop --cfg 4 --seed 42 --lora lora/xeno_klein_v2.safetensors; echo RENDER_DONE' > redraw/g_weltall/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/g_weltall/infer.log; ls /workspace/redraw/g_weltall/res/v2 | wc -l"
   (done: RENDER_DONE and 63 files)

Download, stop the pod:
   scp -P PORT -r root@HOST:/workspace/redraw/g_weltall/res ai\redraw\g_weltall\

Install (RetroArch closed):
   python tools\gear_redraw.py install --dir ai\redraw\g_weltall
