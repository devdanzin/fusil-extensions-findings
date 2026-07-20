# solders — findings index

[**solders**](https://github.com/kevinheavey/solders) is the Solana Python SDK, a **Rust/PyO3**
extension (wrapping the `solana-*` crates). fusil fuzzed it via `--modules=solders
--packages=solders` with `--concurrency-stress` and `--new-uninit`; the fleets **converged very
fast** onto a handful of panic sites.

## Environment

- **Target / runner Python:** `/home/danzin/projects/labeille/venvs/fuzz-solders/bin/python`
  — CPython **3.14.4+ debug build** (`heads/3.14:d42874a1ba6`), ASan-instrumented, GIL on
  (`GIL_MODES="1"`). Has `solders` **0.28.0** + fusil + python-ptrace installed.
- **fusil flags** (fleet 02, the productive one): `--concurrency-stress --tsan-threads 4
  --tsan-iterations 200 --new-uninit --child-memory-limit-mb 4096 --functions-number 30
  --classes-number 15 --methods-number 10 --objects-number 30`. Config: `~/fleet_solders.conf`.
- **Fleets:** `fusil-solders_01` (~215 kept), `fusil-solders_02` (~1490 kept — the `--new-uninit`
  run), `fusil-solders_03` (~52 kept). All converged fast to the sites below.

## Findings

| id | site | panic reason | veh | minimal repro |
|----|------|--------------|-----|---------------|
| **SOLDERS-0001** | `solana-epoch-schedule-3.0.0/src/lib.rs:100` | `assertion failed: slots_per_epoch >= MINIMUM_SLOTS_PER_EPOCH` | 1124 | `EpochSchedule(0)` |
| **SOLDERS-0002** | `crates/rpc-responses/src/lib.rs:2044` | `unwrap()` on serde `invalid type: integer, expected a map` | 435 | `batch_to_json([0])` |
| **SOLDERS-0003** | `crates/pubkey/src/lib.rs:266` | `unwrap()` on `TryFromSliceError(())` | 52 | `Pubkey.from_bytes(b"x")` |

All three are **PyO3 panics caught as `pyo3_runtime.PanicException`** (exit 1 + a Rust backtrace on
stderr), where a clean `ValueError`/`TypeError` is expected — the panic-on-bad-input class
(`notes/pyo3-panic-class.md`). SOLDERS-0001 is by far the dominant crash; its `assert!` lives in the
*dependency* crate `solana-epoch-schedule`, but the fix belongs in solders (validate before
forwarding). SOLDERS-0002/0003 are in solders' own crates (`rpc-responses`, `pubkey`).

## Crash-bucket breakdown (all 3 fleets)

- **~1557 `panicked`** = the three sites above (1124 epoch-schedule + 435 rpc-responses + 52 pubkey,
  minus overlap). All PyO3-caught `PanicException`.
- **~107 `assertion`** (incl. `cpu_load-assertion`) = a **CPython** debug-build assertion
  `PyStackRef_BoolCheck(cond)` in `_PyEval_EvalFrameDefault` (SIGABRT under ASan). **This is a known
  CPython bug — [python/cpython#153354](https://github.com/python/cpython/issues/153354) — not a
  solders bug**, incidentally hit during solders fuzzing. Excluded here; see
  `notes/excluded-cpython-153354.md`.
- **~70 `cpu_load-panicked`** = the same panic sites under a CPU-load watchdog kill.

## Status

Converged: no crash outside the three panic sites + the excluded CPython assertion. All three now
have deterministic 1-line repros (SOLDERS-0002's direct trigger, `batch_to_json([0])`, was pinned by
instrumenting the `--new-uninit` discovery sweep).

**Prior art** (`notes/prior-art.md`): the PyO3 panic-on-bad-input class is **known** to the solders
maintainer (issues #122/#108/#91, and merged fix PR #93 "Avoid panic in `Keypair.from_base58_string`"),
but our **three specific sites appear unreported** — no issue names EpochSchedule/slots_per_epoch,
`batch_to_json`, or `Pubkey.from_bytes`. They are new instances of a class the maintainer already fixes.
Next step — (maintainer's call) file the three panics, framed as more `#93`-style panics.
