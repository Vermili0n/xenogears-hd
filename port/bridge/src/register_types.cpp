#include "xeno_core.h"

#include <gdextension_interface.h>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/core/defs.hpp>
#include <godot_cpp/godot.hpp>

using namespace godot;

static void InitializeXeno(ModuleInitializationLevel Level)
{
	if (Level == MODULE_INITIALIZATION_LEVEL_SCENE)
	{
		GDREGISTER_CLASS(XenoCore);
	}
}

static void UninitializeXeno(ModuleInitializationLevel)
{
}

extern "C"
{
	GDExtensionBool GDE_EXPORT xeno_library_init(GDExtensionInterfaceGetProcAddress GetProcAddress, const GDExtensionClassLibraryPtr Library,
		GDExtensionInitialization* Initialization)
	{
		GDExtensionBinding::InitObject Init(GetProcAddress, Library, Initialization);
		Init.register_initializer(InitializeXeno);
		Init.register_terminator(UninitializeXeno);
		Init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
		return Init.init();
	}
}
