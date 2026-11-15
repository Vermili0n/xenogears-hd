// Fast Xenogears LZSS decoder (same rules as xfs.lzss_decompress) + bulk unpack of disc files.
using System;
using System.Collections.Generic;
using System.IO;

public static class XenoLzss2
{
    public static byte[] Decompress(byte[] data, int offset, out int used)
    {
        int outLen = BitConverter.ToInt32(data, offset);
        used = 0;
        if (outLen <= 0 || outLen > 16 * 1024 * 1024) return null;
        var o = new byte[outLen];
        int p = 0, i = offset + 4, n = data.Length;
        while (p < outLen && i < n)
        {
            int flags = data[i++];
            for (int bit = 0; bit < 8; bit++)
            {
                if (p >= outLen || i >= n) break;
                if ((flags & (1 << bit)) != 0)
                {
                    if (i + 1 >= n) { i = n; break; }
                    int h = data[i] | (data[i + 1] << 8);
                    i += 2;
                    int size = (h >> 12) + 3;
                    int src = p - (h & 0x0FFF) % 4078;
                    for (int k = 0; k < size && p < outLen; k++) { o[p] = src + k >= 0 ? o[src + k] : (byte)0; p++; }
                }
                else o[p++] = data[i++];
            }
        }
        used = i - offset;
        return (p == outLen || used >= data.Length - offset - 4) ? o : null;
    }

    // Reads the hidden TOC from a user-data stream and writes "<n>.dec" for files that decode as LZSS
    // with a plausible size ratio. Returns count written.
    public static int UnpackAll(string user, string outDir, int maxSize)
    {
        Directory.CreateDirectory(outDir);
        byte[] u = File.ReadAllBytes(user);
        int pos = 24 * 2048, n = 0, written = 0;
        while (true)
        {
            if (u[pos] == 0xFF && u[pos + 1] == 0xFF && u[pos + 2] == 0xFF && u[pos + 3] == 0 && u[pos + 4] == 0 && u[pos + 5] == 0 && u[pos + 6] == 0) break;
            int lba = u[pos] | (u[pos + 1] << 8) | (u[pos + 2] << 16);
            int size = BitConverter.ToInt32(u, pos + 3);
            pos += 7;
            int idx = n++;
            if (size <= 32 || size > maxSize) continue;
            long start = (long)lba * 2048;
            if (start + size > u.Length) continue;
            var f = new byte[size];
            Buffer.BlockCopy(u, (int)start, f, 0, size);
            int decLen = BitConverter.ToInt32(f, 0);
            if (decLen < size || decLen > 8 * size || decLen > 4 * 1024 * 1024) continue;
            int used;
            byte[] d = Decompress(f, 0, out used);
            if (d == null || used < size - 2048) continue;
            File.WriteAllBytes(Path.Combine(outDir, idx + ".dec"), d);
            written++;
        }
        return written;
    }
}
