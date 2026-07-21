# CRYPTOGRAPHY-0001 — public `padding.PKCS7(0)` / `ANSIX923(0)` panic (divide/modulo by zero) instead of raising `ValueError` (`src/rust/src/padding.rs`)

**Found by** fusil (`--tsan`) fuzzing the **cryptography** PyO3 extension; cryptography 50.0.0-dev1 (git `49.0.0-227-g2f67c6d`), OpenSSL 3.5.5, target CPython 3.14t **free-threaded + TSan** build (GIL off). Surfaced as the `cryptography_hazmat_bindings__rust-panicked` dir in fleet `fusil-cryptography_02` (`padding.rs:182`). The bug itself is **single-threaded and not free-threading related** — the fleet just happened to import the module and construct a padding context with a fuzzed `block_size`.

## Reproducer

```python
from cryptography.hazmat.primitives import padding

padding.PKCS7(0).unpadder().update(b"A" * 8)   # -> pyo3_runtime.PanicException: attempt to divide by zero
```

All four padding contexts panic with `block_size=0`:

| call | panic | site |
|------|-------|------|
| `PKCS7(0).unpadder().update(...)` | `attempt to divide by zero` | `src/rust/src/padding.rs:182` |
| `ANSIX923(0).unpadder().update(...)` | `attempt to divide by zero` | `src/rust/src/padding.rs:241` |
| `PKCS7(0).padder().finalize()` | `attempt to calculate the remainder with a divisor of zero` | `src/rust/src/padding.rs:103` |
| `ANSIX923(0).padder().finalize()` | `attempt to calculate the remainder with a divisor of zero` | `src/rust/src/padding.rs:147` |

**Caught as:** `pyo3_runtime.PanicException` — PyO3's `catch_unwind` turns the Rust panic into a Python exception, so an uncaught call exits with a Rust backtrace on stderr rather than a hard abort.

**Expected:** `PKCS7(0)` / `ANSIX923(0)` should raise `ValueError` at construction (a block size of 0 is meaningless), exactly as `PKCS7(4)` already does (`block_size must be a multiple of 8`). It must not construct a context that later panics.

**Reliability:** deterministic, single call, single-threaded. Reproduces on any build (the panic is an ordinary `/`/`%` by zero, not a debug-only overflow check).

## Root cause & fix

The public validator accepts `block_size = 0`:

```python
# src/cryptography/hazmat/primitives/padding.py
def _byte_padding_check(block_size: int) -> None:
    if not (0 <= block_size <= 2040):                 # :33  -- lower bound should be 0 <
        raise ValueError("block_size must be in range(0, 2041).")
    if block_size % 8 != 0:                            # :36  -- 0 % 8 == 0, so 0 passes
        raise ValueError("block_size must be a multiple of 8.")
```

`0 <= block_size` admits `0`, and `0 % 8 == 0` admits it again, so `PKCS7(0)`/`ANSIX923(0)` construct successfully. The Rust context stores `block_size / 8` (`src/rust/src/padding.rs:79/123/168/…`), which is `0` for `block_size < 8`, and then divides/modulos by it:

```rust
// unpadder update  (src/rust/src/padding.rs:182 / :241)
let finished_blocks = (v.len() / self.block_size).saturating_sub(1);   // / 0
// padder finalize  (src/rust/src/padding.rs:103 / :147)
let pad_size = self.block_size - (v % self.block_size);                 // % 0
```

**Fix** — reject `block_size == 0` in the validator (and fix the message):

```python
if not (0 < block_size <= 2040):
    raise ValueError("block_size must be in range(1, 2041).")
```

This closes all four sites at once (nothing downstream can then see `self.block_size == 0`). Belt-and-braces, the Rust `new(block_size)` constructors could also reject `block_size == 0`, since `hazmat.bindings._rust` is directly importable and a caller bypassing the Python layer (`_rust.PKCS7PaddingContext(0)`) hits the same panic.

## Why it's a bug even though PyO3 "catches" it

- A plain, documented public call — `padding.PKCS7(0).unpadder().update(data)` — raises `pyo3_runtime.PanicException` (a wrong, un-idiomatic exception type that leaks the crate's internals on stderr) where every other bad `block_size` raises a clean `ValueError`. The validator's own intent is clearly to reject invalid block sizes; `0` slips through an off-by-one.
- `PanicException` is a latent hard crash: PyO3's `catch_unwind` only saves you where PyO3 installed it. The same panic across an FFI boundary that isn't wrapped, or under `panic = "abort"`, is a process abort.
- This is the panic-on-bad-input class (see `../../README.md#the-dominant-bug-class-pyo3-extensions`), here caused by a validator off-by-one rather than a missing check.

## Prior art

Tracker checked 2026-07-21 (`gh api search/issues` on `pyca/cryptography`): **no** existing issue for `block_size=0`, a padding divide-by-zero, or a `PanicException` from `PKCS7`/`ANSIX923`. Unreported.
