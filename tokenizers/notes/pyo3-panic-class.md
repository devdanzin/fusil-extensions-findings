# The panic-on-bad-input class (tokenizers)

Like every PyO3 extension we've fuzzed, tokenizers' dominant Python-reachable crash class is a
**Rust `panic!` on unvalidated Python input** — `.unwrap()`, `.expect()`, an `assert!`, an
unchecked index, or an arithmetic overflow whose failing case is Python-controllable. TOKENIZERS-0001
is the arithmetic-overflow variant (`tokens.len() - 1` underflowing a `usize`).

## Mechanism

PyO3 wraps `#[pyfunction]`/`#[pymethod]` bodies in `std::panic::catch_unwind`, so the panic becomes
a Python `pyo3_runtime.PanicException` rather than aborting the process. The crash is "soft" (an
uncaught call exits 1, not SIGABRT), but it is still wrong:

1. **Wrong exception type** — callers expect `ValueError`/`TypeError` and get `PanicException`, which
   reads as "the library is broken", not "you passed bad input", and can't reasonably be
   caught-and-handled.
2. **Leaks internals** — a multi-KB Rust backtrace naming crate paths and internal types hits stderr.
3. **Latent hard crash** — `catch_unwind` only saves you where PyO3 installed it. A panic across an
   FFI boundary that isn't wrapped (a callback, a non-PyO3-spawned thread, a `panic = "abort"`
   build) is UB / an abort. `--concurrency-stress` (worker threads) is exactly that kind of context.

## tokenizers already treats this as a bug and fixes it

This is not a hypothetical concern for the maintainers — the tracker shows an established pattern of
fixing decoder/model panics on hostile input, which is the strongest framing for reporting new sites:

- **PR #2154** (merged) — *"Do not panic in the Strip decoder on crafted config or short tokens"* —
  same `Decoder::decode_chain` method, sibling decoder. Direct precedent for TOKENIZERS-0001.
- **PR #1699** (merged) — *"Fix panic in DecodeStream::step due to incorrect index usage"*.
- **PR #1859** (open) — *"Fix unsigned integer underflow issue with truncation"* — same `usize`
  underflow mechanism as TOKENIZERS-0001, different site.
- **#2094 [Security] / #2198** — BPE **model** `build()` panics/aborts on a crafted `tokenizer.json`
  (merge buffer overrun) — the load-time analogue.
- Historical `PanicException` reports: #888, #876, #821, #736, #444.

## Detection (for a static pass / future tokenizers review)

Grep the `tokenizers/src/**` Rust for `.unwrap()` / `.expect(` / `assert!` / `panic!` / `[i]` and
arithmetic on lengths (`len() - `, `- 1`) inside `Decoder`/`Model`/`Normalizer`/`PreTokenizer`/
`Processor` trait impls and `#[pymethod]`/`#[new]` bodies where the failing value derives from Python
input (a token list, a `&str`, a deserialized config field). The decoders and the `tokenizer.json`
deserialization paths are the richest — untrusted config fields flow straight into `decode_chain`
(that is the #2154 shape).

## Fix pattern

Validate / use checked arithmetic and return a `PyErr` (or the correct empty/default result):

```rust
// instead of: let n = tokens.len() - 1;
let n = tokens.len().saturating_sub(1);        // empty -> n = 0, map runs zero times, returns []

// instead of: some_field.try_into().unwrap()
let arr: [u8; N] = field.try_into()
    .map_err(|_| PyValueError::new_err("bad length"))?;
```
