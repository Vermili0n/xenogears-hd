# sprites/ - research archive

The scripts that made the HD sprites of the texture pack, kept as they were used. **They are not guaranteed to run**:
they were written for one machine, they read data that is not published (anything extracted from the game,
references, trained weights, rented-GPU outputs), and personal paths, hosts, ports and key names in them were
replaced mechanically by placeholders such as `<XENO_SPRITES>`, `<XENO_PORT>`, `<WORKDIR>`, `<HOME>`,
`<DATA_DRIVE>`, `<RETROARCH_DRIVE>`, `<POD_HOST>`, `<POD_PORT>`, `<JUMP_HOST>`, `<SSH_KEY>`.

Comments in the scripts speak of "the user" (the author) and of "Claude" (the AI assistant the work was done with).

How the pipeline fits together: `../docs/SPRITES.md`.

- `tools/` - extraction, reference and redraw jobs, post-processing, installation into the pack, QA sheets
  (`tools/eyepatch_fix/` - one repair campaign; `tools/prompts/` - prompts for the hosted image model).
- `pod/` - scripts that ran on rented GPU pods (training and rendering) and the local watchers / sync scripts.
- `ai/redraw/` - the later targeted re-renders and fixes, one folder per job (only their scripts and READMEs).
- `ai/pod_v2/` - the training script of the second LoRA version.
- `КАК_ПЕРЕРИСОВАТЬ.md` - the author's step-by-step note (Russian) on re-rendering single frames.
