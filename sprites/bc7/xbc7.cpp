// xbc7 - BC7 encoder for the Xenogears HD pack (30.10.2026).
//
// The Beetle core keeps HD textures in its "PSX convention" (rhi_tt.c convert_tri_to_psx):
//   transparent = exactly (0,0,0,0)   - the shaders test texel == vec4(0.0) EXACTLY
//   opaque      = (r,g,b,0), never all zero (opaque black is stored as (1,1,1,0))
//   semi (STP)  = (r,g,b,255)         - shaders: alpha > 0.5 and alpha as the blend weight
// Plain BC7 is lossy and breaks the exact zero (black fringe around every sprite, holes in dark parts).
// So every block is encoded by bc7enc, decoded back and checked; a block that breaks the rules gets
// one of our own encodings that keep them by construction: colour endpoint 0 = black exactly (BC7
// endpoints of value 0 and weights 0/64 are exact), alpha exactly 0/255 (modes 4/5 have separate alpha
// indices; mode 6 when the whole block has alpha 0).
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "third_party/bc7enc.h"
#include "third_party/bc7decomp.h"

#define EXPORT extern "C" __declspec(dllexport)

static const int W2[4] = {0, 21, 43, 64};
static const int W3[8] = {0, 9, 18, 27, 37, 46, 55, 64};
static const int W4[16] = {0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64};
static inline int lerp6(int e0, int e1, int w) { return ((64 - w) * e0 + w * e1 + 32) >> 6; }

static bc7enc_compress_block_params g_params;

struct Bits {
   uint8_t b[16];
   int pos;
   Bits() { memset(b, 0, 16); pos = 0; }
   void put(uint32_t v, int n) {
      for (int i = 0; i < n; i++, pos++)
         if ((v >> i) & 1) b[pos >> 3] |= (uint8_t)(1 << (pos & 7));
   }
};

struct Blk {
   uint8_t px[16][4];
   bool valid[16];   // inside the image (edge padding is "don't care")
   bool t[16];       // transparent (exact zero)
};

// Rules check against the decoded block; returns false if broken, else the squared error.
static bool check(const Blk &k, const uint8_t dec[16][4], uint64_t *err) {
   uint64_t e = 0;
   for (int i = 0; i < 16; i++) {
      if (!k.valid[i]) continue;
      bool dz = !dec[i][0] && !dec[i][1] && !dec[i][2] && !dec[i][3];
      if (k.t[i] != dz) return false;
      if (k.t[i]) continue;
      int a = k.px[i][3], da = abs((int)dec[i][3] - a);
      if (a == 0 || a == 255) {   // level 0 (and flat mip areas): opaque / semi must stay what they are
         if ((a >= 128) != (dec[i][3] >= 128) || da > 8) return false;
      } else if (da > 48) {       // mip averages of opaque and semi texels: the shaders only test == 0 there
         return false;
      }
      for (int c = 0; c < 4; c++) { int d = (int)dec[i][c] - (int)k.px[i][c]; e += (uint64_t)(d * d); }
   }
   *err = e;
   return true;
}

// ---- own encodings: colour line from exact black (endpoint 0) to e1 -------------------------------
// precision: 5 = mode 4 (5-bit), 7 = mode 5 (7-bit), 8 = mode 6 with p-bit 0 (even values)
static inline int expand(int code, int prec) {
   if (prec == 5) return (code << 3) | (code >> 2);
   if (prec == 7) return (code << 1) | (code >> 6);
   return code << 1;   // mode 6, p-bit 0
}
static inline int maxcode(int prec) { return prec == 5 ? 31 : 127; }
static int nearest_code(int v, int prec) {
   int best = 0, bd = 1 << 30;
   for (int c = 0; c <= maxcode(prec); c++) { int d = abs(expand(c, prec) - v); if (d < bd) { bd = d; best = c; } }
   return best;
}

// For colour endpoint codes e1 (black = endpoint 0), choose per-pixel colour indices (n levels, weights W)
// and return the error. opaque non-transparent pixels may not decode to black (they would become holes).
static uint64_t assign(const Blk &k, const int e1c[3], int prec, const int *W, int n, int idx[16]) {
   int e1[3] = {expand(e1c[0], prec), expand(e1c[1], prec), expand(e1c[2], prec)};
   uint64_t err = 0;
   for (int i = 0; i < 16; i++) {
      if (k.t[i] && k.valid[i]) { idx[i] = 0; continue; }
      uint64_t bd = ~0ull; int bi = n - 1;
      for (int j = 0; j < n; j++) {
         int r = lerp6(0, e1[0], W[j]), g = lerp6(0, e1[1], W[j]), b = lerp6(0, e1[2], W[j]);
         if (k.valid[i] && !r && !g && !b && k.px[i][3] < 128) continue;   // would read as transparent
         int dr = r - k.px[i][0], dg = g - k.px[i][1], db = b - k.px[i][2];
         uint64_t d = (uint64_t)(dr * dr + dg * dg + db * db);
         if (d < bd) { bd = d; bi = j; }
      }
      idx[i] = bi;
      if (bd == ~0ull) return ~0ull;   // e1 too dark: this opaque pixel can only decode to black
      if (k.valid[i]) err += bd;
   }
   return err;
}

static uint64_t fit_line(const Blk &k, int prec, const int *W, int n, int e1c[3], int idx[16]) {
   // start from the per-channel maximum of the non-transparent pixels, then least squares + local search
   double mx[3] = {0, 0, 0};
   for (int i = 0; i < 16; i++)
      if (!k.t[i] || !k.valid[i])
         for (int c = 0; c < 3; c++) if (k.px[i][c] > mx[c]) mx[c] = k.px[i][c];
   for (int c = 0; c < 3; c++) e1c[c] = nearest_code((int)mx[c], prec);
   if (!e1c[0] && !e1c[1] && !e1c[2]) e1c[0] = e1c[1] = e1c[2] = 1;
   uint64_t best = assign(k, e1c, prec, W, n, idx);
   for (int it = 0; it < 4; it++) {
      double num[3] = {0, 0, 0}, den = 0;
      for (int i = 0; i < 16; i++) {
         if (k.t[i] && k.valid[i]) continue;
         double w = W[idx[i]] / 64.0;
         den += w * w;
         for (int c = 0; c < 3; c++) num[c] += w * k.px[i][c];
      }
      if (den <= 0) break;
      int cand[3];
      for (int c = 0; c < 3; c++) { double v = num[c] / den; cand[c] = nearest_code(v < 0 ? 0 : v > 255 ? 255 : (int)(v + 0.5), prec); }
      int ci[16];
      uint64_t e = assign(k, cand, prec, W, n, ci);
      if (e < best) { best = e; memcpy(e1c, cand, sizeof(cand)); memcpy(idx, ci, sizeof(ci)); } else break;
   }
   for (bool improved = true; improved;) {   // greedy +-1 / +-2 per channel
      improved = false;
      for (int c = 0; c < 3; c++)
         for (int d = -2; d <= 2; d++) {
            if (!d) continue;
            int cand[3] = {e1c[0], e1c[1], e1c[2]};
            cand[c] += d;
            if (cand[c] < 0 || cand[c] > maxcode(prec)) continue;
            int ci[16];
            uint64_t e = assign(k, cand, prec, W, n, ci);
            if (e < best) { best = e; memcpy(e1c, cand, sizeof(cand)); memcpy(idx, ci, sizeof(ci)); improved = true; }
         }
   }
   return best;
}

// alpha: endpoint A0 = 0, A1 = a1 (expanded value); 2-bit indices, nearest level per pixel (binary 0/255
// alpha is exact; mip averages of opaque and semi texels are approximated); transparent pixels use 0
static int max_alpha(const Blk &k) {
   int m = 0;
   for (int i = 0; i < 16; i++) if (!k.t[i] && k.px[i][3] > m) m = k.px[i][3];
   return m;
}
static void alpha_plan(const Blk &k, int a1, int aidx[16]) {
   for (int i = 0; i < 16; i++) {
      int bj = 0, bd = 1 << 30;
      if (!(k.t[i] && k.valid[i]))
         for (int j = 0; j < 4; j++) { int d = abs(lerp6(0, a1, W2[j]) - k.px[i][3]); if (d < bd) { bd = d; bj = j; } }
      aidx[i] = bj;
   }
}

static void enc_mode6(const Blk &k, uint8_t out[16]) {   // only when every pixel has alpha 0
   int e1c[3], idx[16];
   fit_line(k, 8, W4, 16, e1c, idx);
   int e0c[3] = {0, 0, 0};
   if (idx[0] >= 8) {   // anchor index must have its MSB clear: swap endpoints, invert indices
      for (int c = 0; c < 3; c++) { int t = e0c[c]; e0c[c] = e1c[c]; e1c[c] = t; }
      for (int i = 0; i < 16; i++) idx[i] = 15 - idx[i];
   }
   Bits b;
   b.put(1 << 6, 7);
   for (int c = 0; c < 3; c++) { b.put(e0c[c], 7); b.put(e1c[c], 7); }
   b.put(0, 7); b.put(0, 7);   // alpha 0, 0
   b.put(0, 1); b.put(0, 1);   // p-bits 0
   b.put(idx[0], 3);
   for (int i = 1; i < 16; i++) b.put(idx[i], 4);
   memcpy(out, b.b, 16);
}

static void enc_mode5(const Blk &k, uint8_t out[16]) {
   int e1c[3], cidx[16], aidx[16], a1;
   fit_line(k, 7, W2, 4, e1c, cidx);
   a1 = max_alpha(k);
   alpha_plan(k, a1, aidx);
   int e0c[3] = {0, 0, 0}, a0 = 0;
   if (cidx[0] >= 2) {
      for (int c = 0; c < 3; c++) { int t = e0c[c]; e0c[c] = e1c[c]; e1c[c] = t; }
      for (int i = 0; i < 16; i++) cidx[i] = 3 - cidx[i];
   }
   if (aidx[0] >= 2) { int t = a0; a0 = a1; a1 = t; for (int i = 0; i < 16; i++) aidx[i] = 3 - aidx[i]; }
   Bits b;
   b.put(1 << 5, 6);
   b.put(0, 2);   // rotation
   for (int c = 0; c < 3; c++) { b.put(e0c[c], 7); b.put(e1c[c], 7); }
   b.put(a0, 8); b.put(a1, 8);
   b.put(cidx[0], 1); for (int i = 1; i < 16; i++) b.put(cidx[i], 2);
   b.put(aidx[0], 1); for (int i = 1; i < 16; i++) b.put(aidx[i], 2);
   memcpy(out, b.b, 16);
}

static void enc_mode4(const Blk &k, uint8_t out[16]) {   // idxMode 1: colour 3-bit indices, alpha 2-bit
   int e1c[3], cidx[16], aidx[16], a1;
   fit_line(k, 5, W3, 8, e1c, cidx);
   int a1c = (max_alpha(k) + 2) >> 2;   // 6-bit code, expands as (c << 2) | (c >> 4)
   if (a1c > 63) a1c = 63;
   a1 = (a1c << 2) | (a1c >> 4);
   alpha_plan(k, a1, aidx);
   int e0c[3] = {0, 0, 0}, a0 = 0;
   if (cidx[0] >= 4) {
      for (int c = 0; c < 3; c++) { int t = e0c[c]; e0c[c] = e1c[c]; e1c[c] = t; }
      for (int i = 0; i < 16; i++) cidx[i] = 7 - cidx[i];
   }
   if (aidx[0] >= 2) { int t = a0; a0 = a1c; a1c = t; for (int i = 0; i < 16; i++) aidx[i] = 3 - aidx[i]; }
   Bits b;
   b.put(1 << 4, 5);
   b.put(0, 2);   // rotation
   b.put(1, 1);   // idxMode
   for (int c = 0; c < 3; c++) { b.put(e0c[c], 5); b.put(e1c[c], 5); }
   b.put(a0, 6); b.put(a1c, 6);
   b.put(aidx[0], 1); for (int i = 1; i < 16; i++) b.put(aidx[i], 2);   // 2-bit set = alpha
   b.put(cidx[0], 2); for (int i = 1; i < 16; i++) b.put(cidx[i], 3);   // 3-bit set = colour
   memcpy(out, b.b, 16);
}

static void decode(const uint8_t blk[16], uint8_t dec[16][4]) {
   bc7decomp::color_rgba p[16];
   bc7decomp::unpack_bc7(blk, p);
   for (int i = 0; i < 16; i++) memcpy(dec[i], p[i].m_comps, 4);
}

// 0 = bc7enc, 1 = own mode 6, 2 = own mode 5, 3 = own mode 4, -1 = no encoding keeps the rules
static int encode_block(const Blk &k, uint8_t out[16]) {
   uint8_t dec[16][4];
   uint64_t err, best = ~0ull;
   int how = -1;
   uint8_t cand[16];
   bc7enc_compress_block(cand, k.px, &g_params);
   decode(cand, dec);
   if (check(k, dec, &err)) { memcpy(out, cand, 16); return 0; }
   bool all_a0 = true;
   for (int i = 0; i < 16; i++) if (k.px[i][3]) all_a0 = false;
   for (int m = 1; m <= 3; m++) {
      if (m == 1 && !all_a0) continue;
      if (m == 1) enc_mode6(k, cand); else if (m == 2) enc_mode5(k, cand); else enc_mode4(k, cand);
      decode(cand, dec);
      if (check(k, dec, &err) && err < best) { best = err; memcpy(out, cand, 16); how = m; }
   }
   return how;
}

EXPORT void xbc7_init(int uber, int perceptual) {
   bc7enc_compress_block_init();
   bc7enc_compress_block_params_init(&g_params);
   if (!perceptual) bc7enc_compress_block_params_init_linear_weights(&g_params);
   g_params.m_uber_level = (uint32_t)uber;
}

// rgba: w*h*4 (PSX convention); out: ceil(w/4)*ceil(h/4)*16 bytes.
// stats[0..5] += blocks, empty, bc7enc, own mode 6, own mode 5, own mode 4. Returns the number of
// blocks no encoding could keep the rules for (the caller keeps such a texture uncompressed).
EXPORT int xbc7_encode(const uint8_t *rgba, int w, int h, uint8_t *out, int64_t *stats) {
   int bw = (w + 3) / 4, bh = (h + 3) / 4, failed = 0;
   static const uint8_t EMPTY[16] = {0x40, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};   // mode 6, all zero
   for (int by = 0; by < bh; by++)
      for (int bx = 0; bx < bw; bx++) {
         Blk k;
         bool empty = true;
         for (int i = 0; i < 16; i++) {
            int x = bx * 4 + (i & 3), y = by * 4 + (i >> 2);
            k.valid[i] = x < w && y < h;
            int sx = x < w ? x : w - 1, sy = y < h ? y : h - 1;
            memcpy(k.px[i], rgba + ((size_t)sy * w + sx) * 4, 4);
            k.t[i] = !k.px[i][0] && !k.px[i][1] && !k.px[i][2] && !k.px[i][3];
            if (k.valid[i] && !k.t[i]) empty = false;
         }
         uint8_t *o = out + ((size_t)by * bw + bx) * 16;
         stats[0]++;
         if (empty) { memcpy(o, EMPTY, 16); stats[1]++; continue; }
         int how = encode_block(k, o);
         if (how < 0) { failed++; memcpy(o, EMPTY, 16); } else stats[2 + how]++;
      }
   return failed;
}

EXPORT void xbc7_decode(const uint8_t *blocks, int w, int h, uint8_t *rgba) {
   int bw = (w + 3) / 4, bh = (h + 3) / 4;
   for (int by = 0; by < bh; by++)
      for (int bx = 0; bx < bw; bx++) {
         uint8_t dec[16][4];
         decode(blocks + ((size_t)by * bw + bx) * 16, dec);
         for (int i = 0; i < 16; i++) {
            int x = bx * 4 + (i & 3), y = by * 4 + (i >> 2);
            if (x < w && y < h) memcpy(rgba + ((size_t)y * w + x) * 4, dec[i], 4);
         }
      }
}
