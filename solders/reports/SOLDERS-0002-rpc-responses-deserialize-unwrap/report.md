# SOLDERS-0002 — solders.rpc.responses.batch_to_json() .unwrap()s a serde deserialize error -> panic on a non-response element (crates/rpc-responses/src/lib.rs:2044)

**Found by** fusil (`--new-uninit`) fuzzing the **solders** PyO3 extension; solders 0.28.0 (target:
CPython 3.14.4+ debug build, GIL on). **435 crash dirs** across fleets 01–03.

## Reproducer

```python
from solders.rpc.responses import batch_to_json

batch_to_json([0])   # element 0 -> "invalid type: integer `0`, expected a map" -> panic
# batch_to_json(b"a")  # equivalent: bytes iterate to ints; 0x61 == 97 -> "integer `97`, expected a map"
```

`batch_to_json([])` and `batch_to_json(b"")` are fine (no elements); `batch_to_json("a")` raises a
proper `TypeError`. The panic needs a **non-empty iterable whose elements are not RPC responses**.

**Panic:** `` called `Result::unwrap()` on an `Err` value: Error("invalid type: integer `N`, expected a map", line: 1, column: 2) ``
(site: `crates/rpc-responses/src/lib.rs:2044`, crate: rpc-responses — solders' own)

**Caught as:** `pyo3_runtime.PanicException` — PyO3's `catch_unwind` turns the Rust panic into a
Python exception, so the process exits 1 (not a hard abort) but prints a multi-KB Rust panic
backtrace to stderr and raises an un-idiomatic `PanicException`.

**Expected:** a Python `TypeError`/`ValueError` naming the bad element, not a `PanicException`.

**Reliability:** deterministic (single call).

## Root cause & fix

`solders.rpc.responses.batch_to_json(seq)` batch-serializes a sequence of RPC response objects. It
iterates `seq` and, for each element, round-trips it through serde (deserializing it as a response,
i.e. a JSON **map**) before serializing — and `.unwrap()`s that deserialize `Result` at
`crates/rpc-responses/src/lib.rs:2044`. When an element is not a response (a bare integer — e.g.
`[0]`, or a byte from `b"a"` which iterates to `97`), the deserialize returns
`Err(invalid type: integer N, expected a map)` and the `.unwrap()` panics.

This was the not-yet-pinned finding in the original catalog entry; it was elusive because the
module's *parsers* (`parse_websocket_message`, `parse_notification`, `batch_from_json`) and all 139
`*Resp.from_json` classmethods return a *clean* error on a bare integer — only `batch_to_json`
`.unwrap()`s. It surfaced 435× in the fleet via the `--new-uninit` discovery sweep, which calls
module-level callables with hostile arg combos (`b"a"`, `[]`, `{}`, a stateful bomb whose `__str__`
returns the varying integers `97`/`116`/… seen in the panic reasons).

**Fix:** propagate the serde error as a `PyErr` (`?` / `map_err(|e| PyValueError::new_err(...))`)
instead of `.unwrap()`, and/or validate that each `seq` element is a response object up front.
