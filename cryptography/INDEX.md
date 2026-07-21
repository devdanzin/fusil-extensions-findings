# cryptography — findings index

[**cryptography**](https://github.com/pyca/cryptography) (pyca/cryptography) is the standard Python
cryptography library; its `hazmat.bindings._rust` module is a **Rust/PyO3** extension (built on the
`openssl` crate + OpenSSL/libcrypto, with cryptography's own Rust in `src/rust/`). fusil fuzzed it in
**`--tsan`** mode on a free-threaded ThreadSanitizer CPython.

## Environment

- **Target / runner Python:** `/home/danzin/projects/labeille/venvs/tsan-cryptography/bin/python`
  — CPython **3.14t free-threaded + ThreadSanitizer** (`--disable-gil`), GIL off. Has
  **cryptography 50.0.0-dev1** (editable, git `49.0.0-227-g2f67c6d`) + OpenSSL **3.5.5**. Full
  detail: `notes/environment.md`.
- **Fleets:** `fusil-cryptography_01` (pre-fusil-#237, 18 crash dirs) and `fusil-cryptography_02`
  (10+ crash dirs). `--tsan` concurrency-stress.

## Findings

| id | site | panic reason | veh | minimal repro |
|----|------|--------------|-----|---------------|
| **CRYPTOGRAPHY-0001** | `src/rust/src/padding.rs:103/147/182/241` | divide / modulo by zero | 1 | `padding.PKCS7(0).unpadder().update(b"A"*8)` |

**CRYPTOGRAPHY-0001** is a **PyO3 panic caught as `pyo3_runtime.PanicException`** where a clean
`ValueError` is expected — the panic-on-bad-input class (`../README.md#the-dominant-bug-class-pyo3-extensions`),
here caused by a **validator off-by-one**: `_byte_padding_check`
(`src/cryptography/hazmat/primitives/padding.py:33`) accepts `block_size=0` (`0 <= block_size`
should be `0 <`), so `PKCS7(0)`/`ANSIX923(0)` construct and then the Rust context divides/modulos by
`block_size/8 = 0` at four sites (unpadder `.update`, padder `.finalize`). **Reachable via the public
API**, deterministic, single-threaded (not free-threading related). One-line fix (`0 < block_size`).
See `reports/CRYPTOGRAPHY-0001-.../report.md`.

## Crash-bucket breakdown (both fleets, ~28 dirs) — only 1 is cryptography

- **1** = CRYPTOGRAPHY-0001 (the `_rust-panicked` dir).
- **7** = a **CPython** `memoryview` iterator race (`memoryiter_next`), *not* cryptography — the
  non-atomic `it_index` cursor + the `it_seq` exhaustion **double-DECREF** (a UAF), cataloged as
  **TSAN-0055** in [`cpython-tsan-findings`](https://github.com/devdanzin/cpython-tsan-findings)
  (sibling of dict TSAN-0053/cpython#154130 and set TSAN-0054/cpython#144357). Incidental to
  cryptography (it exposes buffers → fusil shared a `memoryview`).
- **6** = an **OpenSSL** concurrent EC-keygen race inside libcrypto (`EcKey::generate`), *not*
  cryptography/CPython (libcrypto uninstrumented; likely a known OpenSSL pattern or TSan FP).
- **14** = **cpython#120321** shared-generator cascade (`_01`, pre-fusil-#237 op-h noise), known
  CPython.

Full evidence for the excluded buckets: `notes/environment.md`.

## Status

One cryptography finding (CRYPTOGRAPHY-0001), deterministic public-API repro, prior-art checked
(unreported). Next step — (maintainer's call) file CRYPTOGRAPHY-0001 with pyca/cryptography, framed
as "public `PKCS7`/`ANSIX923` accept `block_size=0` and then panic (divide-by-zero) instead of
raising `ValueError`."
