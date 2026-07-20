# tokenizers fuzzing environment & how to reproduce

## Paths (host: the fusil dev box)

- **Venv (target + runner):** `/home/danzin/projects/labeille/venvs/fuzz-tokenizers-ft/bin/python`
  — CPython **3.14.6+ free-threaded** build (`heads/3.14:07efb08123b`), `--disable-gil
  --with-pydebug --with-address-sanitizer --without-pymalloc`, Clang 21. Has `tokenizers`
  **0.23.2.dev0** (editable, src HEAD `b62132e` at
  `/home/danzin/projects/laruche/repositories/tokenizers`) + fusil + python-ptrace installed.
- **tokenizers Rust source:** `/home/danzin/projects/laruche/repositories/tokenizers` — the core
  crate is `tokenizers/` (the panic site is `tokenizers/src/decoders/bpe.rs:28`), the PyO3 layer is
  `bindings/python/`. The installed `.so` is a Rust **debug / overflow-checks** build and is **not**
  ASan-instrumented (only CPython is).
- **Fleet config:** `~/fleet_tokenizers.conf` (`GIL_MODES="0"`, `INSTANCES=6`,
  `--concurrency-stress --tsan-threads 4 --tsan-iterations 200 --child-memory-limit-mb 4096
  --modules=tokenizers --packages=tokenizers`).
- **Fleet:** `/home/fusil/runs/fusil-tokenizers_01` (4 instances kept, ~727 crash dirs — 41 the
  TOKENIZERS-0001 panic, ~686 the excluded CPython FT race; see
  `excluded-cpython-tsan-0006.md`). Single-threaded and `--new-uninit` follow-up fleets found **no
  new tokenizers crashes**.

## Reproduce the finding

```bash
PY=/home/danzin/projects/labeille/venvs/fuzz-tokenizers-ft/bin/python
"$PY" tokenizers/reports/TOKENIZERS-0001-*/repro.py    # -> pyo3_runtime.PanicException, exit 1
```

Do **not** wrap the target under `ulimit -v` — the ASan CPython reserves a ~20 TB shadow map and
`ulimit -v` makes it fail to start (`ReserveShadowMemoryRange failed`). It is a soft (caught) panic,
so a bare call exits **1** with a Rust `panicked at .../decoders/bpe.rs:28` backtrace on stderr, not
by signal.

**Build caveat:** the panic requires **overflow checks** (this debug build has them). On a release
build `BPEDecoder().decode([])` returns `[]` without crashing (the underflowed `n` is never read for
empty input) — the bug is real but debug-visible only. See the report.

## Re-run a fleet

```bash
cd /home/danzin/projects/fusil/fleet
FLEET_CONF=~/fleet_tokenizers.conf ./fleet check     # preflight
sudo FLEET_CONF=~/fleet_tokenizers.conf ./fleet up 6
FLEET_CONF=~/fleet_tokenizers.conf ./fleet status    # mode/crash/NEW counts (mode auto-detected)
```

`--concurrency-stress` on this **free-threaded** CPython mostly measures *CPython*, not tokenizers:
the stress region hammers generic shared Python objects/iterators from 4 threads and reliably trips
CPython's own free-threading races (which dominate the crash pile). To actually mine tokenizers,
prefer a single-threaded fleet, or unmask concurrency by running on a CPython build with the
`itertools.count` repr race (cpython#153908 / TSAN-0006) fixed. See `excluded-cpython-tsan-0006.md`.
