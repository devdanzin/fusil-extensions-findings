"""CRYPTOGRAPHY-0001 -- public padding.PKCS7(0)/ANSIX923(0) panic with divide/modulo by zero.

`_byte_padding_check` (src/cryptography/hazmat/primitives/padding.py:32) accepts block_size=0
(`if not (0 <= block_size <= 2040)` -- the lower bound should be `0 <`). The Rust context then
stores `block_size / 8 = 0` and divides/modulos by it:

  - unpadder().update():  src/rust/src/padding.rs:182 (PKCS7), :241 (ANSIX923)  -> "divide by zero"
  - padder().finalize():  src/rust/src/padding.rs:103 (PKCS7), :147 (ANSIX923)  -> "remainder ... divisor of zero"

Each reaches Python as pyo3_runtime.PanicException instead of a clean ValueError.
Deterministic, single-threaded (NOT free-threading related).

Run: `python repro.py`  (any interpreter with cryptography installed).
"""
from cryptography.hazmat.primitives import padding


def show(label, fn):
    try:
        fn()
        print(f"{label}: NO panic (unexpected)")
    except BaseException as e:  # noqa: BLE001 -- PanicException is a BaseException
        print(f"{label}: {type(e).__module__}.{type(e).__name__}: {str(e).splitlines()[0]}")


# block_size=0 passes the public validator (bug: `0 <= block_size` should be `0 <`)
padding.PKCS7(0)      # constructs fine
padding.ANSIX923(0)   # constructs fine

show("PKCS7(0).unpadder().update(b'A'*8)", lambda: padding.PKCS7(0).unpadder().update(b"A" * 8))
show("ANSIX923(0).unpadder().update(b'A'*8)", lambda: padding.ANSIX923(0).unpadder().update(b"A" * 8))

def _pkcs7_pad():
    p = padding.PKCS7(0).padder(); p.update(b""); p.finalize()
def _ansix923_pad():
    p = padding.ANSIX923(0).padder(); p.update(b""); p.finalize()
show("PKCS7(0).padder().finalize()", _pkcs7_pad)
show("ANSIX923(0).padder().finalize()", _ansix923_pad)
