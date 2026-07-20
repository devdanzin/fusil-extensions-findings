# SOLDERS-0003 — Pubkey.from_bytes(len != 32) panics via .unwrap() on TryFromSliceError (crates/pubkey/src/lib.rs:266)

**Found by** fusil (`--concurrency-stress` / `--new-uninit`) fuzzing the **solders** PyO3 extension; solders 0.28.0 (target: CPython 3.14.4+ debug build, GIL on). **52 crash dirs** across fleets 01–03.

## Reproducer

```python
from solders.pubkey import Pubkey

Pubkey.from_bytes(b"x")  # any bytes whose length != 32 panics; from_bytes(bytes(32)) is fine
```

**Panic:** `called `Result::unwrap()` on an `Err` value: TryFromSliceError(())`
(site: `crates/pubkey/src/lib.rs:266`, crate: pubkey (solders' own crate))

**Caught as:** `pyo3_runtime.PanicException` — PyO3's `catch_unwind` turns the Rust panic into a Python exception, so the process exits 1 (not a hard abort) but prints a multi-KB Rust panic backtrace to stderr and raises an un-idiomatic `PanicException`.

**Expected:** a Python ValueError (from_bytes should check len == 32 and raise, not unwrap).

**Reliability:** deterministic (single call, no concurrency).

## Root cause & fix

`solders.pubkey.Pubkey.from_bytes(b)` converts the input bytes to a `[u8; 32]` with `TryInto::try_into(...).unwrap()` at crates/pubkey/src/lib.rs:266. Any input whose length is not exactly 32 makes the `try_into` return `Err(TryFromSliceError(()))`, and the `.unwrap()` panics -> `pyo3_runtime.PanicException` (exit 1 + Rust backtrace on stderr) instead of a clean `ValueError`. Confirmed for len 0/1/31/33; `from_bytes(bytes(32))` is fine. Fix = check the length and raise a `PyValueError` (or propagate the `TryFromSliceError` via `?`).
