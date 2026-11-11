#!/usr/bin/env python3
"""Starter fingerprint matcher for the Magic Pencil library.

Reads the reference library (the per-material CSVs in captures/)
and matches scans the way FINDINGS.md says works: Euclidean
distance over the 22 raw log sample/reference ratios,
unstandardized. z-scores hurt; do not add them back.

Two modes:

    python3 scripts/match.py report
    python3 scripts/match.py identify <scan.csv>

`report` runs leave-one-repeat-out over the published library:
for every scan with a same-object sibling, does its nearest
neighbor belong to the same object? This is the number FINDINGS.md
quotes; running it here re-derives it from the data.

`identify` classifies a fresh 22-row scan.csv (the format
scripts/vispek_client.py writes) against the library and answers
with the nearest object, or with UNKNOWN when nothing is close
enough. The distance bands in FINDINGS.md set the reject line: a
nearest neighbor always answers, and a confident wrong answer is
worse than no answer. Recalibrate --max-distance for your own
library; the default comes from ours.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

ALL = list(range(22))
CLEAN = [2] + list(range(16, 22))    # 405 nm + the NIR family
MID = [c for c in ALL if c not in CLEAN]   # the leaky mid-visible
CAPTURES = Path(__file__).resolve().parent.parent / "captures"
MAX_DISTANCE = 0.05   # measured cross-path ceiling minus margin; FINDINGS.md


def load_library():
    """Every scan from the library files (lib-*.csv): one
    (key, log-ratio) per scan. The prefix is the filter -- nothing
    else in captures/ is library data, and a new lib-<material>.csv
    is picked up automatically. The class key is material + item:
    item strings carry no polymer words, so material is part of
    the identity."""
    out = []
    for path in sorted(CAPTURES.glob("lib-*.csv")):
        with open(path) as fh:
            for r in csv.DictReader(fh):
                logr = []
                ok = True
                for i in ALL:
                    s = int(r[f"sample_{i:02d}"])
                    ref = int(r[f"reference_{i:02d}"])
                    if s <= 0 or ref <= 0:
                        ok = False
                        break
                    logr.append(math.log(s / ref))
                if ok:
                    out.append({"key": f"{r['material']} {r['item']}",
                                "logr": logr})
    return out


def dist(a, b, channels=ALL):
    return math.sqrt(sum((a[c] - b[c]) ** 2 for c in channels))


def zdist(a, b, z, channels=ALL):
    return math.sqrt(sum(
        ((a[c] - z[c][0]) / z[c][1] - (b[c] - z[c][0]) / z[c][1]) ** 2
        for c in channels))


def zscores(entries):
    out = []
    for c in ALL:
        col = [e["logr"][c] for e in entries]
        m = sum(col) / len(col)
        sd = math.sqrt(sum((x - m) ** 2 for x in col) / len(col)) or 1.0
        out.append((m, sd))
    return out


def loro(entries, channels=ALL, z=None):
    """Leave-one-repeat-out top-1. Returns (ok, trials, misses)."""
    by_item = {}
    for e in entries:
        by_item.setdefault(e["key"], []).append(e)
    ok = trials = 0
    misses = []
    for e in entries:
        if len(by_item[e["key"]]) < 2:
            continue    # a lone repeat cannot find a sibling
        trials += 1
        if z is None:
            near = min((dist(e["logr"], o["logr"], channels), o)
                       for o in entries if o is not e)
        else:
            near = min((zdist(e["logr"], o["logr"], z, channels), o)
                       for o in entries if o is not e)
        if near[1]["key"] == e["key"]:
            ok += 1
        else:
            misses.append((e["key"], near[1]["key"], near[0]))
    return ok, trials, misses


def report(entries):
    print(f"library: {len(entries)} reference scans\n")

    print("== leave-one-repeat-out, top-1 (all 22 channels) ==")
    z = zscores(entries)
    ok, trials, _ = loro(entries)
    print(f"   raw log-ratio  {ok}/{trials} ({100 * ok / trials:.0f}%)")
    ok, trials, _ = loro(entries, z=z)
    print(f"   z-scored       {ok}/{trials} ({100 * ok / trials:.0f}%)")
    ok, trials, _ = loro(entries, CLEAN)
    print(f"   clean 7 only   {ok}/{trials} ({100 * ok / trials:.0f}%)")
    ok, trials, _ = loro(entries, MID)
    print(f"   mid-visible 15  {ok}/{trials} ({100 * ok / trials:.0f}%)")

    ok, trials, misses = loro(entries)
    if misses:
        print("\n== confusions (all-22 raw) ==")
        for q, a, d in misses:
            print(f"   {q}  ->  {a}  (d={d:.3f})")
    else:
        print("\nno confusions at all-22 raw")


def identify(entries, scan_path, max_distance):
    with open(scan_path) as fh:
        rows = [(int(r["sample"]), int(r["reference"]))
                for r in csv.DictReader(fh)]
    if len(rows) != 22:
        sys.exit(f"{scan_path}: {len(rows)} rows, expected 22")
    if any(s <= 0 or r <= 0 for s, r in rows):
        sys.exit(f"{scan_path}: a channel has a non-positive reading")
    logr = [math.log(s / r) for s, r in rows]

    by_item = {}
    for e in entries:
        by_item.setdefault(e["key"], []).append(e["logr"])

    ranked = []
    for item, vecs in by_item.items():
        best = min(dist(logr, v) for v in vecs)
        spread = None
        if len(vecs) >= 2:
            spread = max(dist(a, b) for i, a in enumerate(vecs)
                         for b in vecs[i + 1:])
        ranked.append((best, item, spread))
    ranked.sort()

    print(f"{'object':<44} {'distance':>9} {'lib spread':>10}")
    for d, item, spread in ranked[:5]:
        s = f"{spread:.3f}" if spread is not None else "n/a"
        print(f"{item:<44} {d:>9.3f} {s:>10}")

    d, item, spread = ranked[0]
    print()
    if d <= max_distance:
        print(f"answer: {item}   (d={d:.3f}, reject line {max_distance})")
        if spread is not None and d > 5 * spread:
            # inside the reject line, but far outside this object's own
            # repeat spread: near-neighbor territory (FINDINGS.md) --
            # the same-color confusions live here
            print(f"caution: d is {d / spread:.0f}x this object's own "
                  f"repeat spread ({spread:.3f}); a near-twin could "
                  "land here too. Compare against the spread, not "
                  "only the reject line.")
    else:
        print(f"answer: UNKNOWN. nearest library object is {item} at "
              f"d={d:.3f}, beyond the reject line {max_distance}.")
        print("Scan the object a few times and add it as a reference; "
              "the library grows exactly this way.")


def main():
    p = argparse.ArgumentParser(
        description="Magic Pencil fingerprint matcher (starter engine)")
    p.add_argument("mode", choices=["report", "identify"])
    p.add_argument("scan", nargs="?", help="scan.csv to identify")
    p.add_argument("--max-distance", type=float, default=MAX_DISTANCE,
                   help="reject line for identify (default from "
                        "FINDINGS.md calibration)")
    args = p.parse_args()

    entries = load_library()
    if not entries:
        sys.exit(f"no reference scans found under {CAPTURES}")

    if args.mode == "report":
        report(entries)
    elif not args.scan:
        sys.exit("identify needs a scan.csv path")
    else:
        identify(entries, args.scan, args.max_distance)


if __name__ == "__main__":
    main()
