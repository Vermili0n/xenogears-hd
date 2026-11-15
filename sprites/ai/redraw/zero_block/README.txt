Frames the production render lost (a layout block '0'): 3 frames + their head close-ups = 5 jobs,
seeds 7, 11, 23 -> 15 pictures, about 3 min on one L40S.

Pod (HOST / PORT from RunPod "Connect -> SSH over exposed TCP"; key ~/.ssh/<SSH_KEY> or ~/.ssh/<SSH_KEY>).
Run from the xeno_sprites folder in PowerShell.

1. A fresh pod only (skip when setup_infer.log already ends with SETUP_OK):
   scp -P PORT pod\setup_infer.sh pod\infer_pod.py root@HOST:/workspace/
   ssh -p PORT root@HOST "mkdir -p /workspace/lora /workspace/redraw"
   scp -P PORT lora\klein_v4\xeno_klein_v4.safetensors root@HOST:/workspace/lora/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup bash setup_infer.sh > setup_infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/setup_infer.log"        (repeat until SETUP_OK, ~10 min)

2. Upload and render (the seeds one after the other, run.sh):
   ssh -p PORT root@HOST "mkdir -p /workspace/redraw"
   scp -P PORT -r ai\redraw\zero_block root@HOST:/workspace/redraw/
   ssh -p PORT root@HOST "cd /workspace && (setsid nohup bash redraw/zero_block/run.sh > redraw/zero_block/infer.log 2>&1 &)"
   ssh -p PORT root@HOST "tail -2 /workspace/redraw/zero_block/infer.log; ls /workspace/redraw/zero_block/res_*/v4 | grep -c png"
   (done: RENDER_DONE and 15 files, 5 per seed)

3. Download, then stop the pod in RunPod:
   scp -P PORT -r root@HOST:/workspace/redraw/zero_block/res_* ai\redraw\zero_block\

4. Tell Claude. Do NOT run fix_apply.py on this folder: these frames are not in ai/prod (jobs_v4.json, meta.json), and
   fix_apply rebuilds the whole h_bart group, which would undo the fixes of 01.11 and 03.11.

What the install has to do (meta.json here has each frame's set, frame, head window and names):
  h_citan__3924_0_039: 69375a47-9694422f, f5c68a74-9694422f
  h_citan__2991_0_116: 52d944e6-177a4dc6, 98658317-177a4dc6, 5d4aab65-177a4dc6, d8d0f8aa-177a4dc6
  h_bart__430_0_070: c2be06fd-84f5630b, ef212788-84f5630b, 9e3e77d0-84f5630b
  ai_redraw.Hero must leave block '0' out for these frames (HeroZ in make_job.py), or compose / slice raise.
  Only the names listed are written; every other part of these frames is in the pack already.

Needs no pod: three more names of Citan's run are cut from composites that exist (the field frames are the world map
set's frames without the head, texel for texel; the field set cuts the body into other blocks):
  4c19563e-9694422f (24x13)                      field 429_0:93 = world map 3924_0:33 -> ai/prod_work/h_citan/work/3924_0_033_red.png
  93b3328f-9694422f (20x21), 938162c3-9694422f (16x10)   field 429_0:97 = world map 3924_0:37 -> ai/prod_work/h_citan/work/3924_0_037_red.png
  (429_0:99 also shows 4c19563e, one texel lower than in 429_0:93.)

Not here: Billy's gear on the field (extracted/disc1_full/gear456, frames 21-30, 65 names) has the same cause; gears are
LoRA v2 (tools/gear_redraw.py).
