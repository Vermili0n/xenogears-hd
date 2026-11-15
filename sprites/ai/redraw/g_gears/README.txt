Field gear g_gear444 50, g_gear445 50, g_gear446 50, g_gear447 55, g_gear448 75, g_gear449 50, g_gear451 50, g_gear452 50, g_gear454 50, g_gear455 30, g_gear456 42, g_gear457 24, g_gear458 25: 601 frames (part cover of 815), about 150 min on one L40S. LoRA v2, seed 42.

Pod (HOST / PORT from RunPod; run from the xeno_sprites folder in PowerShell). A fresh pod: setup as in
КАК_ПЕРЕРИСОВАТЬ.md step 3.1, plus the gear LoRA:
   scp -P PORT lora\klein_v2\xeno_klein_v2.safetensors root@HOST:/workspace/lora/

Upload and render:
   ssh -p PORT root@HOST "mkdir -p /workspace/redraw"
   scp -P PORT -r ai\redraw\g_gears root@HOST:/workspace/redraw/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup sh -c 'HF_HOME=/workspace/hf python infer_pod.py --jobs redraw/g_gears/jobs.json --out redraw/g_gears/res --crop --cfg 4 --seed 42 --lora lora/xeno_klein_v2.safetensors; echo RENDER_DONE' > redraw/g_gears/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/g_gears/infer.log; ls /workspace/redraw/g_gears/res/v2 | wc -l"
   (done: RENDER_DONE and 601 files)

Download, stop the pod:
   scp -P PORT -r root@HOST:/workspace/redraw/g_gears/res ai\redraw\g_gears\

Install (RetroArch closed):
   python tools\gear_redraw.py install --dir ai\redraw\g_gears
