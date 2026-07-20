# TOKENIZERS-0001 — BPEDecoder.decode([]) panics via usize underflow on empty input (tokenizers/src/decoders/bpe.rs:28)

**Found by** fusil (`--concurrency-stress`) fuzzing the **tokenizers** PyO3 extension; tokenizers 0.23.2.dev0 (src HEAD `b62132e`), target CPython 3.14.6+ **free-threaded + ASan + debug** build (GIL off). **41 crash dirs** in fleet `fusil-tokenizers_01` — the *only* tokenizers bug in the fleet (the other ~686 crash dirs are a CPython free-threading race, not tokenizers; see `notes/excluded-cpython-tsan-0006.md`).

## Reproducer

```python
from tokenizers.decoders import BPEDecoder

BPEDecoder().decode([])   # empty token list -> usize underflow at decoders/bpe.rs:28
```

**Panic:** `attempt to subtract with overflow`
(site: `tokenizers/src/decoders/bpe.rs:28`, crate: `tokenizers` — the core Rust crate)

**Caught as:** `pyo3_runtime.PanicException` — PyO3's `catch_unwind` turns the Rust panic into a Python exception, so an uncaught call exits 1 (not a hard abort) after printing a multi-KB Rust panic backtrace to stderr and raising an un-idiomatic `PanicException`.

**Expected:** `decode([])` should return `[]` (decoding an empty token list is empty). It must not panic.

**Reliability:** deterministic (single call, no concurrency). **Build-dependent — debug / overflow-checks only:** the panic fires eagerly on a build with integer-overflow checks on (this debug build). On a release build the subtraction wraps to `usize::MAX`, but `n` is never read for empty input (the `map` runs zero times), so release returns `[]` and does *not* crash. Still a real latent bug (see below).

## Root cause & fix

`BPEDecoder::decode_chain` computes the last-token index up front without guarding the empty case:

```rust
// tokenizers/src/decoders/bpe.rs
fn decode_chain(&self, tokens: Vec<String>) -> Result<Vec<String>> {
    let n = tokens.len() - 1;            // line 28: 0usize - 1 underflows when tokens is empty
    Ok(tokens
        .into_iter()
        .enumerate()
        .map(|(i, token)| {
            let replacement = if i == n { "" } else { " " };   // n only read here
            token.replace(&self.suffix, replacement)
        })
        .collect())
}
```

For empty `tokens`, `tokens.len()` is `0` and `0 - 1` underflows the `usize`. With overflow checks (debug) that panics immediately at the `let n = ...` line, *before* the iterator runs. In release the value wraps to `usize::MAX` and is never read (the map iterates zero times), so the result is correct by accident — the code is only non-crashing because of a coincidence, not because the empty case is handled.

**Fix** — guard the empty case / use a saturating or checked subtraction:

```rust
let n = tokens.len().saturating_sub(1);   // empty -> n = 0, map runs zero times, returns []
```

or an explicit `if tokens.is_empty() { return Ok(vec![]); }`.

## Why it's a bug even though PyO3 "catches" it, and even though release doesn't crash

- On any **overflow-checks** build (debug, or a release build with `overflow-checks = true`), a plain Python call `BPEDecoder().decode([])` raises `pyo3_runtime.PanicException` instead of returning `[]` — a wrong, uncatchable-in-practice exception type that leaks the crate's internals on stderr.
- The non-crash in release is **incidental** (`n` happens never to be read for empty input). Any future edit that reads `n` on the empty path — or a downstream `panic = "abort"` / cross-FFI-thread context (exactly what `--concurrency-stress` exercises) — turns this into a hard crash.
- This is the same class and the same method (`Decoder::decode_chain`) the maintainers already fixed for a sibling decoder in **[#2154](https://github.com/huggingface/tokenizers/pull/2154)** ("Do not panic in the Strip decoder on crafted config or short tokens"), and the same `usize`-underflow mechanism as open **[#1859](https://github.com/huggingface/tokenizers/pull/1859)** (truncation underflow). See `../../notes/prior-art.md` / this extension's `notes/prior-art.md`.

## Prior art

The specific site (`BPEDecoder` / `decoders/bpe.rs` empty-input underflow) is **unreported**. The panic-on-bad-input class is well known and actively fixed in tokenizers; closest matches are #2154 (Strip `decode_chain` panic, **merged**) and #1859 (truncation `usize` underflow, open). Full search in `notes/prior-art.md`.
