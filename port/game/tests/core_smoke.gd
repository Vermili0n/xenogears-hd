extends SceneTree
## The bridge without drawing, stage by stage: -- stage=N stops after stage N with exit code 10 + N, so a crash
## shows as the stage that never returned. godot --headless --path game --script res://tests/core_smoke.gd -- stage=N


func _init() -> void:
	var last := 99
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("stage="):
			last = int(arg.substr(6))
	_run(last)


func _run(last: int) -> void:
	if last < 0: return _done(-1)
	var core := XenoCore.new()
	if last == 0: return _done(0)
	var games := ProjectSettings.globalize_path("res://").path_join("../weltall/Games").simplify_path()
	var error := core.open(games)
	printerr("smoke: open '", error, "' ", games)
	if last == 1: return _done(1)
	printerr("smoke: enter '", core.enter_field(1), "'")
	if last == 2: return _done(2)
	for frame in 60:
		error = core.step(0, 128, 128, false)
		if not error.is_empty():
			printerr("smoke: step ", frame, " -> ", error)
			break
	printerr("smoke: info ", core.info())
	if last == 3: return _done(3)
	printerr("smoke: vram bytes ", core.vram().size())
	if last == 4: return _done(4)
	var world := ArrayMesh.new()
	printerr("smoke: world blends ", core.fill_world(world), " surfaces ", world.get_surface_count())
	if last == 5: return _done(5)
	var screen := ArrayMesh.new()
	printerr("smoke: screen blends ", core.fill_screen(screen))
	printerr("smoke: view ", core.view_transform())
	_done(6)


func _done(stage: int) -> void:
	printerr("smoke: done after stage ", stage)
	quit(10 + stage)
