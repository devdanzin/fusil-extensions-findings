# SOLDERS-0002 — solders.rpc.responses .unwrap()s a serde deserialize error -> panic on non-map input (crates/rpc-responses/src/lib.rs:2044)

**Found by** fusil (`--concurrency-stress` / `--new-uninit`) fuzzing the **solders** PyO3 extension; solders 0.28.0 (target: CPython 3.14.4+ debug build, GIL on). **435 crash dirs** across fleets 01–03.

## Reproducer

```python
# SOLDERS-0002 has no minimal 1-liner yet -- it is reached by the fusil --new-uninit region
# (T.__new__(T) on solders.rpc.responses types, then poking their methods). The class is a
# serde_json deserialize `.unwrap()` at crates/rpc-responses/src/lib.rs:2044 that panics when a
# JSON value that is not a map/object (e.g. a bare integer) reaches a map-expecting deserialize.
# Vehicle (reproduces the crates/rpc-responses/src/lib.rs:2044 panic 2/2):
#   /home/fusil/runs/fusil-solders_02/inst-*/python/solders_rpc_responses-panicked-*/source.py
#
# `parse_websocket_message` / `parse_notification` / `_batch_from_json` and every `*Resp.from_json`
# tested with a bare-integer JSON return a *clean* error, so the offending path is a different,
# not-yet-pinned deserialize site behind the uninitialized-object poke -- documented as a class.
import solders.rpc.responses  # see notes; minimal direct trigger pending
```

**Panic:** `called `Result::unwrap()` on an `Err` value: Error("invalid type: integer `N`, expected a map", ...)`
(site: `crates/rpc-responses/src/lib.rs:2044`, crate: rpc-responses (solders' own crate))

**Caught as:** `pyo3_runtime.PanicException` — PyO3's `catch_unwind` turns the Rust panic into a Python exception, so the process exits 1 (not a hard abort) but prints a multi-KB Rust panic backtrace to stderr and raises an un-idiomatic `PanicException`.

**Expected:** a Python exception (ValueError/TypeError) from the deserialize error, not a PanicException.

**Reliability:** vehicle reproduces 2/2 (source.py); minimal direct repro pending.

## Root cause & fix

A serde_json deserialize `.unwrap()` in solders' own rpc-responses crate (crates/rpc-responses/src/lib.rs:2044) panics with `invalid type: integer N, expected a map` when a JSON value that is not an object reaches a map-expecting deserialize. Reached in the fleet by the fusil `--new-uninit` region (`T.__new__(T)` on rpc.responses types, then method poking) -- vehicle reproduces the exact site 2/2. The direct minimal trigger is not yet pinned: the module-level parsers (`parse_websocket_message`, `parse_notification`, `_batch_from_json`) and all 139 `*Resp.from_json` classmethods return a *clean* error on a bare-integer JSON, so the panic is a different deserialize path behind an uninitialized/poked object. Class = a Python-reachable serde `.unwrap()` that should propagate as a `PyErr`. Fix = map the serde error to a PyO3 exception (`?`/`map_err`) instead of `.unwrap()`.
