extends SceneTree
## Godot's own licence and its third-party notices, as the engine carries them (Engine.get_license_text,
## get_copyright_info, get_license_info), written into a folder: the mod folder's LICENSES (tools/make_dist.py).
##   Godot_console.exe --headless --script tools/godot_licenses.gd -- <folder>


func _initialize() -> void:
	var folder: String = OS.get_cmdline_user_args()[0]
	DirAccess.make_dir_recursive_absolute(folder)
	var info := Engine.get_version_info()
	var main := FileAccess.open(folder.path_join("Godot_LICENSE.txt"), FileAccess.WRITE)
	main.store_string("Godot Engine %s (%s)\n\n%s" % [info.string, info.hash, Engine.get_license_text()])
	main.close()
	var notes := FileAccess.open(folder.path_join("Godot_THIRDPARTY.txt"), FileAccess.WRITE)
	notes.store_string("Third-party components of Godot Engine %s, as Engine.get_copyright_info() lists them, and their licences.\n\n" % info.string)
	for component in Engine.get_copyright_info():
		notes.store_string("%s\n" % component.name)
		for part in component.parts:
			notes.store_string("  files: %s\n" % ", ".join(part.files))
			notes.store_string("  copyright: %s\n" % "; ".join(part.copyright))
			notes.store_string("  license: %s\n" % part.license)
		notes.store_string("\n")
	var licenses := Engine.get_license_info()
	for name in licenses.keys():
		notes.store_string("----- License: %s -----\n%s\n\n" % [name, licenses[name]])
	notes.close()
	print("godot_licenses: written to ", folder)
	quit()
