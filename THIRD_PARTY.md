# Third-party components

## In this repository

### bc7enc and bc7decomp in `sprites/bc7/third_party/` (vendored)

`bc7enc.cpp`, `bc7enc.h`, `bc7decomp.cpp`, `bc7decomp.h` by Richard Geldreich, Jr., from bc7enc_rdo
(<https://github.com/richgel999/bc7enc_rdo>), unchanged; the pack's converter `sprites/bc7/xbc7.cpp` is built with
them. Licence: MIT **or** public domain, your choice (`sprites/bc7/third_party/LICENSE`).

### bc7decomp (vendored)

`port/bridge/third_party/bc7decomp/` - `bc7decomp.cpp`, `bc7decomp.h` by Richard Geldreich, Jr., from bc7enc_rdo
(<https://github.com/richgel999/bc7enc_rdo>), unchanged. Decodes the HD pack's BC7 pictures inside the bridge.
Licence: MIT **or** public domain (Unlicense), your choice; the text is at the end of `bc7decomp.cpp`:

```
This software is available under 2 licenses -- choose whichever you prefer.
------------------------------------------------------------------------------
ALTERNATIVE A - MIT License
Copyright(c) 2020 Richard Geldreich, Jr.
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files(the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and / or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions :
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
------------------------------------------------------------------------------
ALTERNATIVE B - Public Domain(www.unlicense.org)
This is free and unencumbered software released into the public domain.
Anyone is free to copy, modify, publish, use, compile, sell, or distribute this
software, either in source code form or as a compiled binary, for any purpose,
commercial or non - commercial, and by any means.
In jurisdictions that recognize copyright laws, the author or authors of this
software dedicate any and all copyright interest in the software to the public
domain.We make this dedication for the benefit of the public at large and to
the detriment of our heirs and successors.We intend this dedication to be an
overt act of relinquishment in perpetuity of all present and future rights to
this software under copyright law.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.IN NO EVENT SHALL THE
AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## Needed to build, not in this repository

### Weltall

The game core. <https://github.com/Roman215/Weltall>, tag `v1.0.3`, commit
`03452af61707b574c310cad2ba057d3577d10a30`, with the four patches in `port/patches/weltall/`. Statically linked into
`xeno_bridge.dll` and `xeno_check.exe` of the release. Licence: MIT.

```
MIT License

Copyright (c) 2026 Roman215

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### godot-cpp

C++ bindings for GDExtension. <https://github.com/godotengine/godot-cpp>, tag `godot-4.5-stable`
(`e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77`). Linked into `xeno_bridge.dll`. Licence: MIT.

```
# MIT License

Copyright (c) 2017-present Godot Engine contributors.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Godot Engine

Godot Engine 4.7.2-stable (official, `ed1daf0bf001b61586d9930840f2f1394092c079`), shipped unmodified in the release
archive (`engine/`). Licence: MIT. Its own third-party components and their licences are listed in the release
archive's `LICENSES/Godot_THIRDPARTY.txt` (generated from `Engine.get_copyright_info()` by
`port/tools/godot_licenses.gd`).

```
Copyright (c) 2014-present Godot Engine contributors (see AUTHORS.md).
Copyright (c) 2007-2014 Juan Linietsky, Ariel Manzur.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Prior work the sprite scripts follow (not verified)

The scripts in `sprites/tools` say in their own headers that their reading of the game's formats follows:

- `xfs.py` - the hidden file table and LZSS: "logic follows andreaukk/XenoTools, MIT".
- `xspr.py`, `mapvram.py`, `npc_tex.py` - the 2D sprite / texture layout: "per rufaswan/Web2D_Games", which the
  header marks as GPL.

Whether these scripts contain code derived from those projects (and what that means for their licence) has not been
checked.

## Not part of this project

Xenogears is a trademark of Square Enix; the game's data is not included anywhere. The Russian fan translation
that the port supports is not included either; the port reads it from the player's own disc image.
`port/data/sprite_alias_table.csv` holds CRC-32 hashes of what the game draws and names of the HD pack's files, no
texels of the game; the content index it stands in for (`sprite_alias_index.bin`, the game's texels) is not published.
