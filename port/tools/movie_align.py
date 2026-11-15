"""A replacement video matched to the core's movie by its pictures (not by its name): for every picture the core
decodes (bridge movie_dump: thumbs.bin, frames.csv) the replacement's frame that looks most like it (normalized
correlation of 64-wide grey thumbnails), then a straight line through them (video time = offset + rate x movie time),
its residual in movie frames, and where the cut diverges (pictures whose best match is far off the line).

    python tools\\movie_align.py <movie_dump folder> <video thumbs .gray> <video fps> [first pts]
        the video's thumbs: ffmpeg -i <video> -an -fps_mode passthrough -vf "crop=...,scale=64:44:flags=area,format=gray"
        -f rawvideo <file>; its frame j is at first_pts + j / fps; or, when <video thumbs>.times is there (one time a
        line, tools/video_thumbs.gd: the video as Godot plays it), at that time.
"""
import os
import csv
import sys

import numpy as np

WIDTH = 64


def normalized(rows):
    rows = rows.astype(np.float32)
    rows -= rows.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    return rows / np.maximum(norms, 1e-6), norms[:, 0]


def main():
    folder, video, fps = sys.argv[1], sys.argv[2], float(sys.argv[3])
    first_pts = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    with open(folder + "/frames.csv") as file:
        frames = list(csv.DictReader(file))
    high = int(frames[0]["thumb_height"])
    movie = np.fromfile(folder + "/thumbs.bin", dtype=np.uint8).reshape(-1, WIDTH * high)
    hd = np.fromfile(video, dtype=np.uint8).reshape(-1, WIDTH * high)
    numbers = np.array([int(f["frame"]) for f in frames])
    m, m_norm = normalized(movie)
    h, h_norm = normalized(hd)
    best = np.zeros(len(m), dtype=np.int64)
    score = np.zeros(len(m), dtype=np.float32)
    for start in range(0, len(m), 512):
        block = m[start:start + 512] @ h.T
        best[start:start + 512] = block.argmax(axis=1)
        score[start:start + 512] = block.max(axis=1)
    movie_time = (numbers - 1) / 15.0
    if os.path.exists(video + ".times"):
        times = np.loadtxt(video + ".times")
        video_time = times[best]
    else:
        video_time = first_pts + best / fps
    # Pictures with detail (not flat black or white) and a clear match carry the line.
    usable = (m_norm > 200) & (score > 0.9)
    rate, offset = np.polyfit(movie_time[usable], video_time[usable], 1)
    for _ in range(3):
        residual = video_time - (offset + rate * movie_time)
        keep = usable & (np.abs(residual) < 0.2)
        rate, offset = np.polyfit(movie_time[keep], video_time[keep], 1)
    residual_frames = (video_time - (offset + rate * movie_time)) * 15.0
    print("pictures %d, video frames %d, usable %d, on the line %d" % (len(m), len(h), usable.sum(), keep.sum()))
    print("video time = %.4f + %.6f x movie time (movie time = (frame - 1) / 15)" % (offset, rate))
    on = residual_frames[keep]
    print("residual on the line, in movie frames: mean %.3f, mean |r| %.3f, max |r| %.3f; within 0.5: %d of %d" % (
        on.mean(), np.abs(on).mean(), np.abs(on).max(), (np.abs(on) <= 0.5).sum(), len(on)))
    off = usable & ~keep
    print("usable pictures off the line (|r| > 3 frames): %d" % off.sum())
    runs = []
    for i in np.where(off)[0]:
        if runs and i - runs[-1][1] <= 15:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    for a, b in runs[:40]:
        print("  frames %d..%d: best video frames %d..%d, scores %.3f..%.3f" % (numbers[a], numbers[b], best[a], best[b], score[a:b + 1].min(), score[a:b + 1].max()))
    # A dozen timestamps across the movie: the match there.
    print("frame, movie s, best video frame, video s, line s, residual frames, score, detail")
    for i in np.linspace(0, len(m) - 1, 14).astype(int):
        print("%5d %8.3f %6d %8.3f %8.3f %7.2f %.4f %6.0f" % (numbers[i], movie_time[i], best[i], video_time[i], offset + rate * movie_time[i],
                                                            residual_frames[i], score[i], m_norm[i]))
    np.savetxt(folder + "/align.csv", np.column_stack([numbers, best, score, m_norm, residual_frames]), delimiter=",",
               header="frame,best_video_frame,score,detail,residual_frames", fmt=["%d", "%d", "%.4f", "%.0f", "%.3f"])


if __name__ == "__main__":
    main()
