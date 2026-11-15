"""Totals of a pack sweep (bridge/src/pack_sweep.cpp): how much of each map's drawing came from the texture pack.

Usage: python tools/sweep_summary.py <sweep.csv> [more part .csv ...] [--merge <out.csv>]
Several part files (one per range of maps) are read together; a map in more than one keeps its last row. --merge writes
them as one CSV sorted by map, and their <part>.missing.txt files as one <out.csv>.missing.txt
("name<TAB>maps seen<TAB>up to five maps").
"""

import argparse
import collections
import csv
import os
import sys

MAPS_KEPT = 5
TOP = 20


def read_rows(paths):
    rows = {}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                rows[int(row["map"])] = row
    return [rows[number] for number in sorted(rows)]


def read_missing(paths):
    """Each name: maps seen (summed over the parts) and up to five of them."""
    seen = {}
    for path in paths:
        missing = path + ".missing.txt"
        if not os.path.exists(missing):
            continue
        with open(missing, encoding="utf-8") as handle:
            for line in handle:
                columns = line.rstrip("\n").split("\t")
                if len(columns) < 2:
                    continue
                count, maps = seen.get(columns[0], (0, []))
                more = [int(x) for x in columns[2].split(",") if x] if len(columns) > 2 else []
                seen[columns[0]] = (count + int(columns[1]), sorted(set(maps + more))[:MAPS_KEPT])
    return seen


def number(row, key):
    return int(row.get(key) or 0)


def share(part, whole):
    return f"{part} of {whole} ({100.0 * part / whole:.2f} %)" if whole else f"{part} of 0"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv", nargs="+")
    parser.add_argument("--merge", help="write the parts as one CSV (and one .missing.txt)")
    args = parser.parse_args()

    rows = read_rows(args.csv)
    missing = read_missing(args.csv)
    if args.merge:
        with open(args.csv[0], newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        with open(args.merge, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
        with open(args.merge + ".missing.txt", "w", encoding="utf-8") as handle:
            for name in sorted(missing):
                count, maps = missing[name]
                handle.write(f"{name}\t{count}\t{','.join(str(m) for m in maps)}\n")

    held = [row for row in rows if not row["error"].startswith("not on this disc")]
    entered = [row for row in held if number(row, "entered")]
    failed = [row for row in held if not number(row, "entered")]
    stopped = [row for row in entered if row["error"]]
    print(f"maps: {len(rows)} rows ({rows[0]['map']}..{rows[-1]['map']}), on disc 1: {len(held)}, stand-ins: {len(rows) - len(held)}")
    print(f"entered: {len(entered)}, failed to enter: {len(failed)}, stopped by an error while running: {len(stopped)}, "
          f"ran all frames: {len(entered) - len(stopped)}")
    moved = [row for row in entered if number(row, "final_map") != int(row["map"])]
    left_field = [row for row in entered if number(row, "final_program") != 1]
    print(f"of the entered: ended on another map {len(moved)}, ended outside the field program {len(left_field)}")
    for title, group in (("failed to enter", failed), ("stopped", stopped)):
        texts = collections.Counter(row["error"] for row in group)
        print(f"\n{title}, by error text:")
        for text, count in texts.most_common(15):
            print(f"  {count:4}  {text}")

    total = collections.Counter()
    for row in rows:
        for key in row:
            if key not in ("map", "entered", "error", "final_map", "final_program"):
                total[key] += number(row, key)
    print("\nsummed over every build (after each 30th frame and the last):")
    print(f"  sprite pieces wholly from the pack: {share(total['sprite_hd'], total['sprite_pieces'])}")
    print(f"  sprite pieces partial: {total['sprite_partial']}, from VRAM: {total['sprite_vram']}")
    print(f"  pieces (sprites and 2D) with no tracked upload: {total['no_upload']}, every upload in the pack yet not from it: {total['all_in_pack']}")
    print(f"  sprite pieces cut with uncovered texels: {total['split_gaps']}")
    print(f"  2D layer wholly from the pack: {share(total['screen_hd'], total['screen_textured'])}")
    scenery = total["scenery_hd"] + total["scenery_vram"]
    print(f"  scenery from pages with pictures: {share(total['scenery_hd'], scenery)}; of those with texels outside the pack's pictures: "
          f"{total['scenery_hd_mixed']}")
    print(f"  unique missing names: {len(missing)}")

    worst = sorted(rows, key=lambda row: number(row, "sprite_pieces") - number(row, "sprite_hd"), reverse=True)[:TOP]
    print(f"\n{TOP} maps with the most sprite pieces not wholly from the pack:")
    print("   map  pieces      hd  partial  vram  no_upload  all_in_pack  missing  error")
    for row in worst:
        if number(row, "sprite_pieces") == number(row, "sprite_hd"):
            break
        print(f"  {row['map']:>4}  {number(row, 'sprite_pieces'):6}  {number(row, 'sprite_hd'):6}  {number(row, 'sprite_partial'):7}  "
              f"{number(row, 'sprite_vram'):4}  {number(row, 'no_upload'):9}  {number(row, 'all_in_pack'):11}  {number(row, 'missing_names'):7}  {row['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
