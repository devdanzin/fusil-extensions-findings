# tokenizers — findings index

[**tokenizers**](https://github.com/huggingface/tokenizers) is Hugging Face's fast tokenizer
library, a **Rust/PyO3** extension (the core `tokenizers` Rust crate + a `bindings/python` PyO3
layer). fusil fuzzed it via `--modules=tokenizers --packages=tokenizers` with `--concurrency-stress`
on a **free-threaded** CPython; the fleet converged to a single tokenizers panic (the rest of the
crash pile is a CPython free-threading race — see below).

## Environment

- **Target / runner Python:** `/home/danzin/projects/labeille/venvs/fuzz-tokenizers-ft/bin/python`
  — CPython **3.14.6+ free-threaded** build (`heads/3.14:07efb08123b`), `--disable-gil --with-pydebug
  --with-address-sanitizer`, GIL off (`GIL_MODES="0"`). Has `tokenizers` **0.23.2.dev0** (editable,
  src HEAD `b62132e`) + fusil + python-ptrace. Full detail: `notes/environment.md`.
- **fusil flags:** `--concurrency-stress --tsan-threads 4 --tsan-iterations 200
  --child-memory-limit-mb 4096 --functions-number 30 --classes-number 15 --methods-number 10
  --objects-number 30`. Config: `~/fleet_tokenizers.conf`.
- **Fleet:** `fusil-tokenizers_01` (4 instances, ~727 crash dirs). Follow-up single-threaded and
  `--new-uninit` fleets found **no new tokenizers crashes** — the surface is essentially mined out at
  this depth.

## Findings

| id | site | panic reason | veh | minimal repro |
|----|------|--------------|-----|---------------|
| **TOKENIZERS-0001** | `tokenizers/src/decoders/bpe.rs:28` | `attempt to subtract with overflow` (`tokens.len() - 1` underflow on empty input) | 41 | `BPEDecoder().decode([])` |

TOKENIZERS-0001 is a **PyO3 panic caught as `pyo3_runtime.PanicException`** where `decode([])` should
return `[]` — the panic-on-bad-input class (`notes/pyo3-panic-class.md`). **Build-dependent:** it
panics only with integer-overflow checks on (this debug build); a release build returns `[]` without
crashing (the underflowed index is never read for empty input). Same class and same trait method
(`Decoder::decode_chain`) as the maintainer-merged Strip-decoder fix
[#2154](https://github.com/huggingface/tokenizers/pull/2154).

## Crash-bucket breakdown (fusil-tokenizers_01, ~727 dirs)

- **41 `panicked`** = TOKENIZERS-0001 (all one site, `decoders/bpe.rs:28`; verified deterministic).
- **~686 `addresssanitizer`** (675 `SEGV` + 11 `ABRT`) = a **CPython free-threading race**, *not*
  tokenizers: the `itertools.count` concurrent-`repr()` UAF in `PyObject_Repr`
  (**TSAN-0006** / [cpython#153908](https://github.com/python/cpython/issues/153908), sibling
  [#153981](https://github.com/python/cpython/issues/153981)). Proven by gdb-resolving a 32-dir
  sample across all 16 module-label families / 2 instances: **32/32 CPython, 0/32 tokenizers.** Plus
  a couple of `genobject.c:261` generator asserts ([cpython#120321](https://github.com/python/cpython/issues/120321)).
  Excluded here; full evidence in `notes/excluded-cpython-tsan-0006.md`.

## Status

Converged: the only tokenizers crash is TOKENIZERS-0001. Deterministic 1-line repro. **Prior art**
(`notes/prior-art.md`): the specific site is **unreported**; the PyO3 decoder-panic class is known
and actively fixed (closest: merged #2154 Strip decoder `decode_chain`, open #1859 truncation
underflow). Next step — (maintainer's call) file TOKENIZERS-0001, framed as the `BPEDecoder`
counterpart of the #2154 Strip-decoder fix.
