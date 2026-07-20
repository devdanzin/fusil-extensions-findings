# solders fuzzing environment & how to reproduce

## Paths (host: the fusil dev box)

- **Venv (target + runner):** `/home/danzin/projects/labeille/venvs/fuzz-solders/bin/python`
  — CPython 3.14.4+ **debug** build, ASan-instrumented, GIL on. `solders` 0.28.0 + fusil +
  python-ptrace installed.
- **Fleet config:** `~/fleet_solders.conf` (`FLEET_DIR=/home/fusil/runs/fusil-solders_03`,
  `INSTANCES=6`, `GIL_MODES="1"`).
- **Fleets:** `/home/fusil/runs/fusil-solders_0{1,2,3}`.

## Reproduce a finding

Each `repro.py` runs directly under the venv python:

```bash
PY=/home/danzin/projects/labeille/venvs/fuzz-solders/bin/python
"$PY" solders/reports/SOLDERS-0001-*/repro.py    # -> pyo3_runtime.PanicException, exit 1
```

A PyO3-caught panic exits **1** (a Python exception), not by signal. To see it is the panic class,
grep stderr for `panicked at` and `PanicException`. SOLDERS-0002 has no 1-liner yet; its vehicle is
`/home/fusil/runs/fusil-solders_02/inst-*/python/solders_rpc_responses-panicked-*/source.py` (run
it under the venv python; it hits `crates/rpc-responses/src/lib.rs:2044`).

## Re-run a fleet

```bash
cd /home/danzin/projects/fusil/fleet
FLEET_CONF=~/fleet_solders.conf ./fleet check     # preflight
sudo FLEET_CONF=~/fleet_solders.conf ./fleet up 6
FLEET_CONF=~/fleet_solders.conf ./fleet status    # mode/crash/NEW counts (mode auto-detected)
```

The fleet ran **without** a dedup catalog (`CATALOG=` empty), so crash dirs are labelled by signal/
kind (`<module>-panicked`, `-assertion`, …), not by bug id. To dedup future solders fleets against
this catalog, point a `--*-dedup-catalog` at `solders/catalog/known_panics.tsv` once fusil grows an
extension-panic deduper (the signature format is documented in the top-level README).
