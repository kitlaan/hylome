#!/usr/bin/env python3
"""Channel-level view of a Magic Pencil scan.

A scan is 22 (sample, reference) pairs; the raw ratio per channel
is the drift-immune quantity (FINDINGS.md). This tool prints it,
plus a two-point reflectance estimate when you point it at white
and dark calibration scans.

    python3 scripts/analyze.py --list
    python3 scripts/analyze.py --scan exploratory-cap
    python3 scripts/analyze.py --scan runs/run-.../scan.csv       # a file path works too

--scan accepts an id from captures/instrument.csv (see --list) or
the path of any 22-row scan.csv, so fresh captures from
vispek_client.py plug straight in.

Defaults: white = the exploratory white-paper scan, dark = the
exploratory black-plastic scan. Those two are EXPLORATORY captures
(see captures/README.md); take fresh controlled ones before
trusting any calibration they produce.
"""

import argparse
import csv
import sys
from pathlib import Path

CAPTURES = Path(__file__).resolve().parent.parent / "captures"
INSTRUMENT = CAPTURES / "instrument.csv"
DEFAULT_WHITE = "exploratory-white-paper"
DEFAULT_DARK = "exploratory-black-plastic"


def pairs_from_columns(r):
    return [(int(r[f"sample_{i:02d}"]), int(r[f"reference_{i:02d}"]))
            for i in range(22)]


def load_scans():
    """Instrument scans by id (the only published scans with ids;
    library rows are addressed by opening their CSV)."""
    out = {}
    with open(INSTRUMENT) as fh:
        for r in csv.DictReader(fh):
            out[r["scan"]] = pairs_from_columns(r)
    return out


def load_scan_file(path):
    with open(path) as fh:
        pairs = [(int(r["sample"]), int(r["reference"]))
                 for r in csv.DictReader(fh)]
    if len(pairs) != 22:
        sys.exit(f"{path}: {len(pairs)} rows, expected 22")
    return pairs


def calibrated(target, white, dark, ch):
    """Dark-subtracted, white-normalized reflectance; None if the
    channel has no usable dynamic range."""
    st, sw, sd = target[ch][0], white[ch][0], dark[ch][0]
    dyn = sw - sd
    if dyn <= 0:
        return None
    return (st - sd) / dyn


def main():
    p = argparse.ArgumentParser(description="Magic Pencil scan analysis")
    p.add_argument("--scan", help="instrument scan id or scan.csv path")
    p.add_argument("--white", default=DEFAULT_WHITE,
                   help=f"white calibration id or path (default {DEFAULT_WHITE})")
    p.add_argument("--dark", default=DEFAULT_DARK,
                   help=f"dark calibration id or path (default {DEFAULT_DARK})")
    p.add_argument("--list", action="store_true", help="list instrument scan ids")
    args = p.parse_args()

    scans = load_scans()
    if args.list:
        for sid in sorted(scans):
            print(sid)
        return
    if not args.scan:
        sys.exit("--scan required (or --list)")

    def resolve(sid, flag):
        # an existing path is a file; anything else is an id
        cand = Path(sid)
        if cand.is_file():
            return load_scan_file(cand)
        if sid in scans:
            return scans[sid]
        sys.exit(f"no instrument scan named {sid!r} and no such file; "
                 f"try --list (or pass a {flag} scan.csv path)")

    target = resolve(args.scan, "--scan")
    white = resolve(args.white, "--white")
    dark = resolve(args.dark, "--dark")

    print(f"{'ch':>2} {'sample':>9} {'reference':>9} {'ratio':>7} {'reflectance':>11}")
    for i in range(22):
        s, r = target[i]
        refl = calibrated(target, white, dark, i)
        shown = f"{refl:.4f}" if refl is not None else "n/a"
        print(f"{i:>2} {s:>9} {r:>9} {s/r:>7.4f} {shown:>11}")


if __name__ == "__main__":
    main()
