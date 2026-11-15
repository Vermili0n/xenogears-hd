"""Summary of a probe_field JSONL run: map, when the field started drawing, the leader, who moved.

Usage: python probe_summary.py <run.jsonl>
"""
import json
import sys


def main(path):
    with open(path, encoding="utf-8") as f:
        frames = [json.loads(line) for line in f if line.strip()]
    stopped = [fr for fr in frames if "stopped" in fr]
    field = [fr for fr in frames if "actors" in fr]
    print(f"frames: {len(frames)}, with field: {len(field)}, stopped: {stopped[0] if stopped else 'no'}")
    if not field:
        return
    print("maps seen:", sorted({fr["map"] for fr in field}))
    drawn = [fr for fr in field if fr.get("scene") == 1]
    running = [fr for fr in field if fr.get("running") == 1]
    print("first frame field running:", running[0]["frame"] if running else None,
          "| first frame scene drawn:", drawn[0]["frame"] if drawn else None)
    if not drawn:
        return
    first, last = drawn[0], drawn[-1]
    leader = last["leader"]
    print(f"leader actor: {leader}; position first {first['actors'][leader]} last {last['actors'][leader]}")
    print(f"camera eye {last['eye']} target {last['target']}")
    print(f"scenery models {last['models']}, polygons {last['polys']}, character quads {last['quads']}, "
          f"2D prims {last['screen_prims']}, characters drawn {len(last['characters'])}")
    moved = []
    for i in range(len(last["actors"])):
        track = [tuple(fr["actors"][i]) for fr in drawn if i < len(fr["actors"])]
        if len(set(track)) > 1:
            path_len = sum(sum(abs(a - b) for a, b in zip(p, q)) for p, q in zip(track, track[1:]))
            moved.append((i, len(set(track)), path_len, track[0], track[-1]))
    print(f"actors: {len(last['actors'])}, moved during the run: {len(moved)}")
    for i, places, path_len, start, end in moved:
        print(f"  actor {i:3}: {places:4} places, path {path_len:6} units, {start} -> {end}")


if __name__ == "__main__":
    main(sys.argv[1])
