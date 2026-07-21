# Recurring PyO3-extension crash shapes (cross-extension)

The per-extension `notes/pyo3-panic-class.md` files describe the dominant crash class in each crate.
This note lifts the **extension-independent** view: the recurring *shapes* fusil has confirmed across
targets, each with the finding(s) that instance it and the guarded-twin (= fix) pattern. A new
extension's fuzzing/triage should start from this checklist.

> **Canonical shape catalog (don't fork it here):** the sibling static-review toolkit maintains the
> authoritative, richer catalog — **`rust-ext-review-toolkit`'s `data/bug_shapes.json`** (15 shapes,
> each with `pattern` / `guarded_twin` / a sibling-`hunt` directive / `caught_as` / `confirmed_examples`
> that already reference the fusil ids below). This note is a fuzzer-side index into it, not a copy —
> a copy would drift. The static repo
> [`rust-ext-review-findings`](https://github.com/devdanzin/rust-ext-review-findings) mirrors this
> catalog's layout and cross-references it (`notes/fuzzer-cross-reference.md`).

## Shapes fusil has confirmed

| shape (toolkit id) | what | fusil finding(s) | guarded twin (the fix) | toolkit agent |
|--------------------|------|------------------|------------------------|---------------|
| **pyresult-unwrap-across-ffi** | `.unwrap()`/`.expect()` on a fallible value in an exposed fn → panic crosses FFI | **SOLDERS-0002** (serde deserialize), **SOLDERS-0003** (`try_into::<[u8;32]>`) | a sibling that `?`-propagates / `map_err(PyValueError…)` — solders' 139 `*Resp.from_json` classmethods | pyresult-propagation-checker |
| **panic-index-slice-in-exposed-fn** | raw index / slice / `a-b` underflow / `assert!` on Python-controlled input | **SOLDERS-0001** (`assert!` on ctor arg), **TOKENIZERS-0001** (empty-input `usize` underflow) | a checked accessor: `.get(i).ok_or_else`, `checked_sub`, early `if !valid { return Err }` | panic-safety-checker |
| **divide-or-modulo-by-zero-on-arg** | `/` or `%` by a Python-controlled value a validator fails to reject as zero | **CRYPTOGRAPHY-0001** (`PKCS7(0)`/`ANSIX923(0)`), **PYDANTIC-0001** (`int_schema(multiple_of=0)`) | a validator that rejects the degenerate value up front; pydantic's own `decimal`/`float` `multiple_of` paths don't panic (decimal raises `DivisionByZero`) | panic-safety-checker |
| **unwrap/unreachable-on-unvalidated-schema** *(a pyresult-unwrap variant)* | builder `unwrap()`/`unreachable!()` on a field the caller was assumed to have validated | **PYDANTIC-0002** (`custom_error_type`/`on_error`/`version`) | the sibling fields that *are* validated at build and return `SchemaError` (e.g. negative `min_length`) | pyresult-propagation-checker |
| **unguarded-recursion → stack overflow** | recursion with no depth guard on Python-controlled nesting → hard `SIGSEGV`/`SIGABRT` | **PYDANTIC-0003** (deep nested `core_schema` at build) | the same crate's *validate/serialize* path **is** recursion-guarded (`RecursionState`/`_recursion_limit` → clean `recursion_loop`); build is not | *(see note below)* |

## Two observations worth carrying back to the static side

- **PYDANTIC-0003 is a recall-gap for the toolkit's `unguarded-recursion-in-dunder` shape.** That
  shape targets recursion in `__eq__`/`__hash__`/`__repr__`; PYDANTIC-0003 is unguarded recursion in a
  **builder** (`build_validator_inner`), not a dunder. The shape wants generalizing to "unguarded
  recursion in any exposed traversal/builder," with the *guarded twin* being a sibling path in the
  same crate that **does** carry a depth guard (pydantic's validate-time `RecursionState`). Good
  feedback for `bug_shapes.json`.
- **Excluded ≠ extension bug.** Several fleet crashes were the *interpreter*, not the extension — the
  tokenizers itertools/generator races (CPython), cryptography's `memoryview`-iterator UAF
  (cpython-tsan **TSAN-0055**) and OpenSSL EC-keygen races in uninstrumented libcrypto. Each is
  recorded in the extension's `notes/excluded-*.md` and tracked upstream, not in the extension catalog.
  The static repo mirrors this separation.

## Pairing with static review (predict → fuzz → confirm)

The two catalogs are two views of the same targets and reinforce each other:

```
   static review (rust-ext-review-toolkit)              fuzzing (fusil)
   scan Rust source for the SHAPES above  ── predicts ──▶ fuzz the built extension with hostile inputs
              ▲                                                    │
              └──────────────  confirms  ◀──────────────────────────┘
```

- **Static predicts dynamic.** Run the toolkit's `panic-safety-checker` / `pyresult-propagation-checker`
  (or `informed-explore`) over an extension's Rust source *before* fuzzing to get a ranked list of
  panic-site candidates; feed those sites to the fuzzer's argument/schema generators so the fuzzer
  targets them. (`fusil_pydantic_plugin` is a natural place to try this next: harvest the candidate
  builders/validators from a static pass, then drive them with hostile `core_schema`s.)
- **Dynamic confirms static.** A statically-flagged site the fuzzer independently crashes is the
  highest-confidence finding this family produces. When the static repo mints the matching
  `RX-<EXT>-NNNN`, it sets `fuzzer_ref` → our `<EXT>-NNNN`; we set the mirror `review_ref` → theirs on
  that one meta (see the README meta-schema). A fuzzer crash the scanner *missed* is a scanner
  recall-gap — a calibration to add on the static side.

Full loop from the static side: `rust-ext-review-findings/notes/fuzzer-cross-reference.md`.
