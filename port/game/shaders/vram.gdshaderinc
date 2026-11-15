// PS1 texture sampling from the whole VRAM (RG8 = a 16-bit unit's low and high bytes), as the GPU samples it:
// 4- and 8-bit pages through their CLUT, 15-bit pages direct; a texel of 0 is transparent; bit 15 marks a texel
// that blends where its primitive is semi-transparent. Per vertex (xeno_session.h): COLOR, UV in texels,
// CUSTOM0 (page x, page y, depth or 3 untextured, flags 1 raw / 2 semi / 4 every texel blends / 8 texture window),
// CUSTOM1 (clut x, clut y, spans the display, place in a battle frame's drawing order),
// CUSTOM2 (first u, first v, last u, last v; -1 unclamped; with flag 8 the window's offset and the bits it replaces).

uniform sampler2D vram : filter_nearest, repeat_disable;

varying flat vec4 look;
varying flat vec4 clut;
varying flat vec4 texels;

uint unit_at(ivec2 p) {
	vec2 rg = texelFetch(vram, p, 0).rg;
	return uint(rg.r * 255.0 + 0.5) | (uint(rg.g * 255.0 + 0.5) << 8u);
}

vec3 srgb_to_linear(vec3 c) {
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c));
}

// The texel's colour (modulated unless raw) and whether it blends; false when it is transparent.
bool psx_texel(vec2 uv, vec3 color, out vec3 rgb, out bool blends) {
	int depth = int(look.z + 0.5);
	int flags = int(look.w + 0.5);
	if (depth == 3) {
		rgb = color;
		blends = true;
		return true;
	}
	ivec2 t = ivec2(floor(uv));
	if ((flags & 8) != 0) {
		// A texture window (a draw mode's, the battle's floor dome): CUSTOM2 holds its offset, then the bits it replaces.
		ivec2 replaced = ivec2(texels.zw);
		t = ((t & ivec2(255)) & ~replaced) | (ivec2(texels.xy) & replaced);
	} else if (texels.z >= 0.0) {
		t = clamp(t, ivec2(texels.xy), ivec2(texels.zw));
	}
	t = t & ivec2(255);
	ivec2 page = ivec2(look.xy);
	ivec2 table = ivec2(clut.xy);
	uint texel;
	if (depth == 0) {
		uint w = unit_at(ivec2(page.x + (t.x >> 2), page.y + t.y));
		texel = unit_at(ivec2(table.x + int((w >> uint((t.x & 3) * 4)) & 15u), table.y));
	} else if (depth == 1) {
		uint w = unit_at(ivec2(page.x + (t.x >> 1), page.y + t.y));
		texel = unit_at(ivec2(table.x + int((w >> uint((t.x & 1) * 8)) & 255u), table.y));
	} else {
		texel = unit_at(page + t);
	}
	if (texel == 0u) {
		return false;
	}
	rgb = vec3(float(texel & 31u), float((texel >> 5u) & 31u), float((texel >> 10u) & 31u)) / 31.0;
	blends = (texel & 0x8000u) != 0u || (flags & 4) != 0;
	if ((flags & 1) == 0) {
		rgb = min(rgb * color * (255.0 / 128.0), vec3(1.0));
	}
	return true;
}
