# SOLDERS-0001 — EpochSchedule(slots_per_epoch < 32) panics via assert! in solana-epoch-schedule (solana-epoch-schedule-3.0.0/src/lib.rs:100)

**Found by** fusil (`--concurrency-stress` / `--new-uninit`) fuzzing the **solders** PyO3 extension; solders 0.28.0 (target: CPython 3.14.4+ debug build, GIL on). **1124 crash dirs** across fleets 01–03.

## Reproducer

```python
from solders.epoch_schedule import EpochSchedule

EpochSchedule(0)  # any slots_per_epoch < MINIMUM_SLOTS_PER_EPOCH (32) panics
```

**Panic:** `assertion failed: slots_per_epoch >= MINIMUM_SLOTS_PER_EPOCH`
(site: `solana-epoch-schedule-3.0.0/src/lib.rs:100`, crate: solana-epoch-schedule (a solders dependency))

**Caught as:** `pyo3_runtime.PanicException` — PyO3's `catch_unwind` turns the Rust panic into a Python exception, so the process exits 1 (not a hard abort) but prints a multi-KB Rust panic backtrace to stderr and raises an un-idiomatic `PanicException`.

**Expected:** a Python ValueError (validate slots_per_epoch >= 32 before constructing).

**Reliability:** deterministic (single call, no concurrency).

## Root cause & fix

solders' `EpochSchedule(slots_per_epoch)` constructor (and `EpochSchedule.custom(...)`) forwards the argument straight into the `solana-epoch-schedule` crate's `EpochSchedule::new`, which does `assert!(slots_per_epoch >= MINIMUM_SLOTS_PER_EPOCH)` (=32) at solana-epoch-schedule-3.0.0/src/lib.rs:100. Any value below 32 (including 0/1/31) fires the assert -> Rust panic -> PyO3 catches it as `pyo3_runtime.PanicException` (process exits 1 with a multi-KB Rust panic backtrace on stderr) instead of a clean `ValueError`. `EpochSchedule(32)` and above are fine. The dominant crash across all three fleets (1124 dirs). NOTE: the assert lives in the *dependency* crate; the fix belongs in solders -- validate `slots_per_epoch` (>= MINIMUM_SLOTS_PER_EPOCH) in the PyO3 constructor and raise a `PyValueError`, rather than passing unvalidated user input into a crate that `assert!`s on it. Also reached via `EpochSchedule.custom(0, 0, True)`.
