#!/usr/bin/env python3
"""Generate <extension>/catalog/known_panics.tsv from <extension>/reports/*/meta.json.

A flat, read-only dedupe snapshot: one `<bug_id>\\t<signature>` row per panic signature. This is
the per-extension analogue of rustpython-findings/scripts/gen_known_panics.py; it lives in each
extension subdir of fusil-extensions-findings and reads only that subdir, so `solders/` and any
future extension each own their catalog. Signatures are panic-site keys
`<crate>-<ver>/src/<path>.rs:<line>` (cargo-registry absolute paths normalised to the crate tail;
an extension's own `crates/...` paths kept as-is). Segfault/abort findings carry no signature
(`"signatures": []`) and contribute no rows.

Run from anywhere: `python3 solders/scripts/gen_known_panics.py`.
"""

import json
import pathlib

# .../<extension>/scripts/gen_known_panics.py -> EXT_ROOT = .../<extension>
EXT_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS = EXT_ROOT / "reports"
OUT = EXT_ROOT / "catalog" / "known_panics.tsv"


def main():
    rows = set()
    ids = set()
    sigless = []
    for meta in sorted(REPORTS.glob("*/meta.json")):
        d = json.loads(meta.read_text())
        if d.get("status") == "folded":
            continue  # retired id, merged into another finding that carries the signature
        rid = d["id"]
        ids.add(rid)
        sigs = [s.strip() for s in d.get("signatures", []) if s.strip()]
        for sig in sigs:
            rows.add((rid, sig))
        if not sigs:
            sigless.append(rid)
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w") as fh:
        fh.write(
            "# bug_id\tsignature   "
            "(panic-site key; cargo-registry paths normalised to <crate>-<ver>/... )\n"
        )
        for rid, sig in sorted(rows):
            fh.write("%s\t%s\n" % (rid, sig))
    print(
        "wrote %s: %d signatures for %d findings"
        % (OUT.relative_to(EXT_ROOT.parent), len(rows), len(ids))
    )
    if sigless:
        print(
            "  (%d finding(s) carry no panic signature -> segv/abort, gdb-resolved: %s)"
            % (len(sigless), ", ".join(sorted(sigless)))
        )


if __name__ == "__main__":
    main()
