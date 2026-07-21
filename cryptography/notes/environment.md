# cryptography fuzzing environment & how to reproduce

## Paths (host: the fusil dev box)

- **Venv (target + runner):** `/home/danzin/projects/labeille/venvs/tsan-cryptography/bin/python`
  — CPython **3.14t free-threaded + ThreadSanitizer** build
  (`/home/danzin/projects/3.14_tsan_debug_ft/python`, `--disable-gil`), GIL off
  (`PYTHON_GIL=0`). Has **cryptography 50.0.0-dev1** (editable, src
  `/home/danzin/projects/laruche/repositories/cryptography` @ `2f67c6d` =
  `49.0.0-227-g2f67c6d`), OpenSSL **3.5.5**, + fusil + python-ptrace.
- **cryptography Rust source:** `/home/danzin/projects/laruche/repositories/cryptography` — the
  PyO3 layer is `src/rust/` (the panic sites are `src/rust/src/padding.rs`), the Python layer is
  `src/cryptography/` (the validator is `src/cryptography/hazmat/primitives/padding.py`). The
  installed `_rust` `.so` is a Rust build; only CPython is TSan-instrumented (OpenSSL/libcrypto
  is not — see the excluded OpenSSL races below).
- **Fleets:** `/home/fusil/runs/fusil-cryptography_01` (pre-#237, 18 crash dirs) and
  `fusil-cryptography_02` (10+ crash dirs). `--tsan` mode (concurrency-stress on the free-threaded
  TSan interpreter): env = `PYTHON_GIL=0`, `TSAN_OPTIONS=halt_on_error=0:...:suppressions=<gateway>`,
  `DEBUGINFOD_URLS=` (llvm-symbolizer hang dodge), `RUST_BACKTRACE=1`.

## Reproduce CRYPTOGRAPHY-0001

```bash
PY=/home/danzin/projects/labeille/venvs/tsan-cryptography/bin/python
PYTHON_GIL=1 DEBUGINFOD_URLS= "$PY" cryptography/repros/CRYPTOGRAPHY-0001_pkcs7_blocksize_zero.py
```

(`PYTHON_GIL=1` is fine — the panic is single-threaded, not free-threading related. Any interpreter
with cryptography installed reproduces it.) Expected: four `pyo3_runtime.PanicException` lines
(divide by zero for the unpadders, remainder-with-divisor-zero for the padders).

## Triage of the cryptography `--tsan` fleets (2026-07-21)

Total ~28 crash dirs across both fleets fall into four buckets — **only one is a cryptography bug**:

- **CRYPTOGRAPHY-0001** (1 dir, `_02` `_rust-panicked`) — the padding `block_size=0` divide/modulo
  panic. The finding.
- **CPython `memoryview` iterator race** (7 dirs, `_02` `tsanNEW`) — pure CPython: a shared
  `memoryview` iterator's non-atomic `it_index` cursor **and** its `it_seq = NULL; Py_DECREF(seq)`
  exhaustion double-DECREF (`memoryiter_next`, `Objects/memoryobject.c`). All frames are CPython
  (`memoryiter_next → builtin_next → _PyEval_EvalFrameDefault`), zero cryptography frames —
  incidental (cryptography exposes buffers, so fusil shared a `memoryview` and iterated it). The
  crash face is a memory-safety UAF, cataloged as **TSAN-0055** in the sibling
  [`cpython-tsan-findings`](https://github.com/devdanzin/cpython-tsan-findings) (sibling of the dict
  TSAN-0053/cpython#154130 and set TSAN-0054/cpython#144357 exhaustion double-DECREFs). **Not
  cryptography.**
- **OpenSSL concurrent EC-keygen race** (6 dirs, `_01`+`_02`, all `asymmetric`) — the race is inside
  **libcrypto** (`memcmp`/`memcpy` on a `CRYPTO_malloc`'d `EcKey` block during concurrent
  `openssl::ec::EcKey::generate`). libcrypto is not TSan-instrumented, so the fusil `tsan_dedup`
  signature collapses onto the CPython `cfunction_vectorcall_FASTCALL_KEYWORDS` call boundary.
  OpenSSL-internal (or a TSan false positive from the uninstrumented lib), **not cryptography, not
  CPython**. A `race:...EcKey...generate` gateway suppression silences it.
- **cpython#120321 shared-generator cascade** (14 dirs, `_01` `assertion-tsanNOPARSE`) —
  `STACK_LEVEL()==0` / `genobject.c:261` / `WITHIN_STACK_BOUNDS` / `frame->stackpointer != NULL`.
  Known CPython, the pre-fusil-#237 op-h shared-generator noise (fusil PR #237 makes op h skip
  generators). `_01` is pre-#237 and is dominated by this pile; `_02` (post-#237) has essentially
  none of it, which is why the memoryview race and OpenSSL races surface there instead.
