# The panic-on-bad-input class (PyO3 extensions)

Every solders finding so far is the same shape, and it is *the* dominant bug class for a PyO3
extension: a **Python-reachable Rust `panic!`** on unvalidated Python input.

## Mechanism

A `#[pyfunction]` / `#[pymethod]` takes Python input and reaches a `.unwrap()`, `.expect()`,
`assert!`, or unchecked index whose failure case is Python-controllable:

- **SOLDERS-0001** — `assert!(slots_per_epoch >= MINIMUM_SLOTS_PER_EPOCH)` on the constructor arg.
- **SOLDERS-0002** — `serde_json` deserialize `.unwrap()` on a value that isn't a map.
- **SOLDERS-0003** — `bytes.try_into::<[u8;32]>().unwrap()` on a wrong-length input.

## What actually happens (and why it's still a bug even though PyO3 "catches" it)

PyO3 wraps extension entry points in `std::panic::catch_unwind`, so the panic becomes a Python
`pyo3_runtime.PanicException` rather than aborting the process. So the crash is "soft": the process
exits 1, not SIGABRT. But it is still wrong:

1. **Wrong exception type.** Callers expect `ValueError`/`TypeError`; they get `PanicException`, a
   type you can't reasonably catch-and-handle and which signals "the library is broken", not
   "you passed bad input".
2. **Leaks internals.** The panic prints a multi-KB Rust backtrace to stderr naming the extension's
   (and its dependencies') crate paths and internal types.
3. **Latent hard crash.** `catch_unwind` only saves you where PyO3 installed it. A panic that
   unwinds across an FFI boundary that *isn't* wrapped (a callback, a thread PyO3 didn't spawn, a
   `panic = "abort"` build) is undefined behaviour / an abort. Fuzzing under `--concurrency-stress`
   (worker threads) is exactly the kind of context where this matters.

## Detection (for a static pass / future extension review)

Grep the extension's Rust for `.unwrap()` / `.expect(` / `assert!` / `panic!` / `[i]` inside
`#[pyfunction]`/`#[pymethod]`/`#[new]` bodies where the failing value derives from a Python argument
(a parsed int, a `&[u8]`, a deserialized JSON). Same tier system as `rustpython-findings/tools/
unwrap_scan`: directly-exposed sites first, then helpers reached from them.

## Fix pattern

Validate and return a `PyErr`:

```rust
// instead of: EpochSchedule::new(slots_per_epoch)  // asserts internally
if slots_per_epoch < MINIMUM_SLOTS_PER_EPOCH {
    return Err(PyValueError::new_err("slots_per_epoch must be >= 32"));
}

// instead of: serde_json::from_str(s).unwrap()
serde_json::from_str(s).map_err(|e| PyValueError::new_err(e.to_string()))?

// instead of: bytes.try_into().unwrap()
let arr: [u8; 32] = bytes.try_into()
    .map_err(|_| PyValueError::new_err("expected 32 bytes"))?;
```
