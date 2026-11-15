"""Sorts the tests a ctest log reports failed into skips and real failures.

With exceptions off (the core's build), Catch2 terminates on SKIP, so a test that only skips because a disc is
missing exits with 0xC0000409 like a crash. Each failed test is run alone; its output tells which it was:
"SKIPPED:" with no failed assertion = a skip, and the skip's message is kept.

Usage: python ctest_triage.py <ctest.log> <WeltallCoreTests.exe> <out.json>
"""
import concurrent.futures
import json
import re
import subprocess
import sys

FAILED = re.compile(r"Test +#\d+: (.+?) \.{3,}.*?(\*\*\*Failed|\*\*\*Exception|\*\*\*Timeout|Not Run)")


def run_one(exe, name):
    # Catch2 test specs treat , [ ] * \ specially: escape them so the name matches only itself.
    spec = re.sub(r"([,\[\]*\\])", r"\\\1", name)
    proc = subprocess.run([exe, spec], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    out = proc.stdout + proc.stderr
    failed_assert = re.search(r"FAILED:|REQUIRE\(|CHECK\(.*\) failed|with expansion:", out) is not None
    skip = re.search(r"SKIPPED:\s*\n(?:explicitly with message:\s*\n)?\s*(.+)", out)
    if skip and not failed_assert:
        kind = "skip"
    elif proc.returncode == 0:
        kind = "passed_alone"
    else:
        kind = "failed"
    return {"name": name, "kind": kind, "code": proc.returncode, "skip": skip.group(1).strip() if skip else None,
            "tail": out[-1500:] if kind == "failed" else None}


def main(log, exe, out_path):
    with open(log, encoding="utf-8", errors="replace") as f:
        names = [m.group(1).rstrip() for m in FAILED.finditer(f.read())]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda n: run_one(exe, n), names))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    kinds = {}
    for r in results:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"failed in ctest: {len(names)} -> {kinds}")
    reasons = {}
    for r in results:
        if r["kind"] == "skip":
            reasons[r["skip"]] = reasons.get(r["skip"], 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  skip x{n}: {reason}")
    for r in results:
        if r["kind"] != "skip":
            print(f"  {r['kind']}: {r['name']} (exit {r['code']})")


if __name__ == "__main__":
    main(*sys.argv[1:4])
