"""PYDANTIC-0001 -- int_schema(multiple_of=0) panics (remainder by zero) at validation.

`SchemaValidator(core_schema.int_schema(multiple_of=0))` builds fine (multiple_of=0 is not
rejected), then validating any int panics: a small int hits the remainder-by-zero at
src/input/return_enums.rs:701; a big int routes through the num-bigint dependency and panics at
num-bigint-0.4.6/src/biguint/division.rs:112. pydantic-core builds panic=unwind, so this surfaces
as pyo3_runtime.PanicException (a clean SchemaError at build or ValidationError at validate is
expected). float(multiple_of=0.0) is fine (f64 % 0.0 = NaN); decimal raises decimal.DivisionByZero.

Run: python repro.py   (any interpreter with pydantic_core).
"""
from pydantic_core import SchemaValidator, core_schema as cs


def show(label, fn):
    try:
        fn()
        print(f"{label}: NO panic")
    except BaseException as e:  # noqa: BLE001
        print(f"{label}: {type(e).__module__}.{type(e).__name__}: {str(e).splitlines()[0]}")


v = SchemaValidator(cs.int_schema(multiple_of=0))  # builds without error -- the bug
show("validate_python(10)   [small int]", lambda: v.validate_python(10))
show("validate_python(10**50)[big int]", lambda: v.validate_python(10**50))
show("validate_json(b'10')", lambda: v.validate_json(b"10"))
