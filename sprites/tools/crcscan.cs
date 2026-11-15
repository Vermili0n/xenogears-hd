// Scans a PSX MODE2/2352 disc image for 32-byte (16 x u16 CLUT) windows whose zlib CRC32
// equals one of the target values. Searches both the raw image and the 2048-byte user-data
// stream (Form 1 payload), at every 2-byte offset.
using System;
using System.Collections.Generic;
using System.IO;

public static class CrcScan
{
    static readonly uint[] T = Make();
    static uint[] Make()
    {
        var t = new uint[256];
        for (uint i = 0; i < 256; i++) { uint c = i; for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1; t[i] = c; }
        return t;
    }

    public static uint Crc(byte[] b, int off, int len)
    {
        uint c = 0xFFFFFFFFu;
        for (int i = 0; i < len; i++) c = T[(c ^ b[off + i]) & 0xFF] ^ (c >> 8);
        return c ^ 0xFFFFFFFFu;
    }

    // Returns "sector:offsetInUserData:target" hits.
    public static List<string> ScanUserData(string bin, uint[] targets, int window)
    {
        var hits = new List<string>();
        var set = new HashSet<uint>(targets);
        long sectors = new FileInfo(bin).Length / 2352;
        const int CHUNK = 4096; // sectors per read
        var raw = new byte[CHUNK * 2352];
        var data = new byte[CHUNK * 2048 + window];
        int carry = 0;
        long baseSector = 0;
        using (var fs = new FileStream(bin, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20))
        {
            while (baseSector < sectors)
            {
                int n = (int)Math.Min(CHUNK, sectors - baseSector);
                int got = fs.Read(raw, 0, n * 2352);
                n = got / 2352;
                if (n == 0) break;
                for (int s = 0; s < n; s++) Buffer.BlockCopy(raw, s * 2352 + 24, data, carry + s * 2048, 2048);
                int len = carry + n * 2048;
                long streamBase = baseSector * 2048 - carry;
                for (int i = 0; i + window <= len; i += 2)
                {
                    uint c = Crc(data, i, window);
                    if (set.Contains(c))
                    {
                        long pos = streamBase + i;
                        hits.Add(string.Format("{0}:{1}:{2:x8}", pos / 2048, pos % 2048, c));
                    }
                }
                // keep the tail so windows crossing chunk borders are not missed
                int keep = Math.Min(window - 2, len);
                Buffer.BlockCopy(data, len - keep, data, 0, keep);
                carry = keep;
                baseSector += n;
            }
        }
        return hits;
    }
}
