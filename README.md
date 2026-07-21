# fusil-extensions-findings

Crashes found by the [fusil](https://github.com/devdanzin/fusil) fuzzer in **native Python
extensions** — Rust/[PyO3](https://pyo3.rs), C, Cython, and friends. Unlike the single-target
sibling catalogs ([`cpython-oom-findings`](https://github.com/devdanzin/cpython-oom-findings),
[`cpython-tsan-findings`](https://github.com/devdanzin/cpython-tsan-findings),
[`rustpython-findings`](https://github.com/devdanzin/rustpython-findings)), this repo is
**multi-target**: one subdirectory per extension, added as we fuzz more.

## Layout

```
<extension>/
  INDEX.md               overview: environment, findings table, fleet history
  reports/<ID>-<slug>/   report.md + repro.py + meta.json   (one per finding)
  repros/                flat copies of every repro.py, named <ID>_<slug>.py
  catalog/known_*.tsv    dedup snapshot: <bug_id>\t<signature>  (per extension)
  scripts/gen_*.py       regenerates the catalog from reports/*/meta.json
  notes/                 class notes, environment, exclusions
```

Findings are identified `<EXT>-NNNN` — the extension name upper-cased, then a zero-padded
counter (`SOLDERS-0001`). IDs never collide across extensions and never get reused.

## Extensions

| extension | kind | findings | notes |
|-----------|------|----------|-------|
| [**solders**](solders/) | Rust / PyO3 (Solana SDK) | **3** (SOLDERS-0001..0003) | converged fast; panic-on-bad-input class |
| [**tokenizers**](tokenizers/) | Rust / PyO3 (Hugging Face) | **1** (TOKENIZERS-0001) | BPE decoder empty-input `usize` underflow; rest of fleet = a CPython FT race, not tokenizers |
| [**cryptography**](cryptography/) | Rust / PyO3 (pyca, on OpenSSL) | **1** (CRYPTOGRAPHY-0001) | public `PKCS7(0)`/`ANSIX923(0)` divide/modulo-by-zero panic (validator off-by-one); rest of fleets = a CPython `memoryview`-iter UAF + OpenSSL EC-keygen race, not cryptography |

## The dominant bug class (PyO3 extensions)

The recurring crash in a PyO3 extension is a **Python-reachable Rust `panic!`** — `.unwrap()`,
`.expect()`, `assert!`, `[i]` out of bounds — on unvalidated Python input. PyO3 wraps
`#[pyfunction]`/`#[pymethod]` bodies in `catch_unwind`, so most such panics surface as a Python
`pyo3_runtime.PanicException` (process exits with a Rust backtrace on stderr) rather than a hard
abort — but they are still bugs: a call that should raise a clean `ValueError`/`TypeError` instead
panics, leaks the extension's Rust internals into a scary message, and is a latent abort in any
context where the unwind isn't caught. The fix is uniformly **validate and return a `PyErr`** (map
the error with `?`/`map_err`, or check preconditions) instead of `.unwrap()`/`assert!`.

A minority are harder: real segfaults (unsafe code), aborts (double-panic, stack overflow), or
crashes in the *interpreter* triggered incidentally during extension fuzzing (tracked as upstream
CPython bugs, not extension findings — see each extension's `notes/`).

## `meta.json` schema (per finding)

```jsonc
{
  "id": "SOLDERS-0001", "extension": "solders", "extension_version": "0.28.0",
  "slug": "...", "title": "...",
  "kind": "panic",                       // panic | segv | abort
  "caught_as": "pyo3_runtime.PanicException",  // or "SIGABRT" / "SIGSEGV"
  "signatures": ["<crate>-<ver>/src/...:LINE"],// panic-site keys (dedup); [] for segv/abort
  "crate": "...", "panic_reason": "...",
  "one_line_repro": "...", "repro": "repro.py",
  "expected": "the Python exception the call should raise instead",
  "vehicles": 1124, "reliability": "...", "status": "confirmed",
  "target_python": "...", "found_in": "...", "confirmed_build": "...",
  "prior_art": "...", "notes": "..."
}
```

The **signature** is a panic-site key `<crate>-<version>/src/<path>.rs:<line>` (cargo-registry
absolute paths — `/…/index.crates.io-…/<crate>-<ver>/…` — are normalised to the `<crate>-<ver>/…`
tail; an extension's own `crates/…` paths are kept as-is). Segfault/abort findings carry no
signature (`"signatures": []`) and are resolved by gdb instead.

## Conventions

- Commit **directly to `main`**, no PRs, no co-author trailer; author as the GitHub noreply
  `74280297+devdanzin@users.noreply.github.com`.
- Outward-facing steps (filing upstream issues with the extension's maintainers) are done by the
  maintainer, not automated.
- **Prior-art search:** before minting/filing, check the extension's tracker with the reliable
  recipe in [`notes/searching-trackers.md`](notes/searching-trackers.md) (use `gh api search/issues`;
  `gh search --state all` is a footgun, and quoting forces phrase-matching).
