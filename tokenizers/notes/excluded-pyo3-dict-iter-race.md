# Excluded: the `dict.rs:578` "dictionary changed size during iteration" panic is known PyO3 behaviour

Two dirs in the `fusil-tokenizers_08` fleet (a TSan-build, `--tsan-mutate-state
--tsan-shared-objects-only` run) panicked with:

```
thread '<unnamed>' panicked at .../pyo3-0.29.0/src/types/dict.rs:578:21:
dictionary changed size during iteration
```

This is **not a bug in tokenizers or in PyO3**, and it is **not a crash / not UB**. It is PyO3's
*documented, by-design* free-threaded dict-iteration behaviour, reached because fusil's mutate-state
ops concurrently mutate a dict that a tokenizers constructor is extracting. This note records the
full evidence so the panic pile isn't mistaken for a tokenizers finding, and so the campaign doesn't
re-chase it.

## What actually panics (full backtrace)

The fleet stdout is truncated after `stack backtrace:` (fusil kills the child on the first
`panicked` match). Re-running the exact crashing `source.py` directly — nothing kills it — caught the
full Rust backtrace (hit on run 12/200, ~8%/run). The load-bearing frames:

```
dict.rs:578   pyo3::types::dict::DictIterImpl::next_unchecked   panic!("dictionary changed size ...")
dict.rs:638   pyo3::types::dict::BoundDictIterator::next        (per-next() critical section)
map.rs:121    HashMap<String,u32> as FromPyObject>::extract     ← iterates the passed dict
models.rs:361 tokenizers::models::PyVocab as FromPyObject>::extract
models.rs:457 tokenizers::models::PyBPE::__pymethod___new____
```

So the iterated dict is **not** the shared object's `__dict__` (the op (d)/(j) target) — it is the
**`vocab` dict *argument*** of `tokenizers.models.BPE(vocab=<dict>, merges=…)`. `PyBPE::__new__`
takes `vocab: Option<PyVocab>` where `PyVocab::Vocab(HashMap<String, u32>)`; PyO3 extracts it by
**iterating the passed dict** via `BoundDictIterator`. When another worker thread mutates that same
dict (op (d)/(j) `setattr`/container churn — any size change), the dict's length changes between two
`next()` calls, and PyO3's CPython-parity check fires.

## Why it panics (mechanism)

`BoundDictIterator::new` records `di_used = dict_len` at iterator creation (dict.rs:793). Each
`next()` runs `next_unchecked` inside a **per-`next()` critical section** (dict.rs:638) and re-reads
`ma_used = dict_len`; if `di_used != ma_used` it does `panic!("dictionary changed size during
iteration")` (dict.rs:576) — a deliberate mirror of CPython's
`RuntimeError: dictionary changed size during iteration`.

- The critical section is taken **per `next()`**, not held across the whole loop, so a concurrent
  mutation between iterations is *allowed* to happen and is *detected* on the next `next()`.
- The `panic!` is **unconditional** (not a `debug_assert!`), so it is **release-affected**, unlike
  the debug-only overflow of TOKENIZERS-0001.
- PyO3's `#[pyfunction]`/`#[new]` trampoline wraps the body in `catch_unwind`, so the panic becomes
  `pyo3_runtime.PanicException` raised **in the calling thread**. The process does **not** abort
  (exit code 0), and there is **no memory unsafety**: the per-`next()` critical section protects the
  actual `PyDict_Next`, and the size-check runs before it.

## Deterministic minimal repro

`../repros/excluded_pyo3_dict_iter_race.py` (~25 lines, no fusil): 4 threads call
`BPE(vocab=shared_dict, merges=[])` while 4 threads grow/shrink `shared_dict`.

- **`PYTHON_GIL=0` → panics on the first run** (`pyo3_runtime.PanicException: dictionary changed size
  during iteration`, one per racing extractor thread; process still exits 0).
- **`PYTHON_GIL=1` → clean 3/3** (single-thread semantics serialise the C-level extraction; no
  cross-thread mutation window).

So it is strictly a **free-threading** effect.

## Prior art — this is documented PyO3 design

- **[PyO3 #4439](https://github.com/PyO3/pyo3/issues/4439)** (*"Make `PyDict` iterator compatible
  with free-threaded build"*, closed) — introduced the per-`next()` `PyCriticalSection` locking that
  produces exactly this behaviour.
- **[PyO3 #4571](https://github.com/PyO3/pyo3/issues/4571)** (*"Add locked iterations APIs for dicts
  and lists"*, closed) — the FT lead states it plainly: *"pyo3 follows Python's behavior for
  multithreaded dict and list iteration and **allows race conditions** … apply a critical section for
  dicts in each loop iteration … [whole-loop locking] would make the semantics for iteration via pyo3
  different than via python."* The panic on a detected size change is the intended parity with
  CPython's `RuntimeError`.

A tracker sweep (2026-07-21) found **no** open issue treating this as a defect, on either
`PyO3/pyo3` or `huggingface/tokenizers`. The tokenizers `PanicException` issues (#1698, #821, #876,
#888, …) are all unrelated (`unwrap`/buffer/thread-pool/missing-token).

## Why both layers are blameless

- **PyO3:** documented design (#4439/#4571). Per-iteration critical section matches Python's
  "iteration allows races" semantics; the size-change panic mirrors `RuntimeError`. The only nit is
  the *rendering* — `pyo3_runtime.PanicException` (with a Rust backtrace to stderr) rather than a
  catchable `RuntimeError` — but that is PyO3's general panic-across-FFI model, not specific to this
  site, and not tracked as a bug.
- **tokenizers:** `extract::<HashMap<String,u32>>()` is the idiomatic way to accept a `vocab` dict.
  The panic requires the **caller** to mutate the `vocab` dict from another thread *while* it is being
  handed to the constructor — a caller-side data race, not a tokenizers defect.

The class generalises to **any** PyO3 extension that extracts a container
(`HashMap`/`BTreeMap`/`Vec<…>`) from a caller-supplied dict/list argument on the free-threaded build,
if the caller concurrently mutates that argument.

## Why it's still worth recording

It is the first crash that reached the **PyO3 binding layer** (argument extraction) rather than
CPython internals — proof that fusil's `--tsan-mutate-state` op-mix exercises an extension's
`FromPyObject` extraction under concurrent mutation. It surfaced only in `fusil-tokenizers_08` because
the dominant #120321 shared-generator noise (op (h)) was removed by fusil PR #237; on noisier fleets
this 2-in-536 signal is buried. The tooling result — mutate-state reaches the binding layer — is the
keeper; the panic itself is known behaviour and is **not filed upstream**.
