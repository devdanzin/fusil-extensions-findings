# PYDANTIC-0001 — `int_schema(multiple_of=0)` panics (remainder/divide by zero) at validation

**Found** during design-phase probing while building the `fusil_pydantic_plugin`; reproduced by the plugin's `seed_multiple_of_zero` factory. pydantic_core **2.41.5**, target CPython 3.14t free-threaded + ASan.

## Reproducer

```python
from pydantic_core import SchemaValidator, core_schema as cs

v = SchemaValidator(cs.int_schema(multiple_of=0))   # builds fine -- multiple_of=0 is NOT rejected
v.validate_python(10)                               # -> pyo3_runtime.PanicException
```

| input | panic | site |
|-------|-------|------|
| `validate_python(10)` (small int) | `attempt to calculate the remainder with a divisor of zero` | `src/input/return_enums.rs:701` |
| `validate_python(10**50)` (big int) | `attempt to divide by zero` | `num-bigint-0.4.6/src/biguint/division.rs:112` (dependency) |
| `validate_json(b"10")` | `attempt to calculate the remainder with a divisor of zero` | `src/input/return_enums.rs:701` |

**Caught as:** `pyo3_runtime.PanicException` (pydantic-core builds `panic = "unwind"`).

**Expected:** `multiple_of=0` should be rejected at build (`SchemaError`) or produce a `ValidationError`; it must not panic. `float_schema(multiple_of=0.0)` is fine (`f64 % 0.0 = NaN`), and `decimal_schema(multiple_of=Decimal(0))` raises `decimal.DivisionByZero` — only the **int** path panics.

## Root cause & fix

`int_schema(multiple_of=0)` builds without complaint; at validation the modulo check `value % multiple_of` divides by zero. Small ints hit the remainder-by-zero in pydantic-core's own `return_enums.rs`; big ints route through the `num-bigint` dependency's division and panic there.

**Fix:** reject `multiple_of <= 0` at build time and raise `SchemaError` (as negative `min_length` and other invalid constraints already do), or guard the modulo at validate time. This is the same panic-on-bad-input shape as `../../cryptography/` **CRYPTOGRAPHY-0001** (a config value that should be rejected instead divides by zero) — build-independent, not a debug-only overflow check.

## Prior art

Unreported (pydantic/pydantic-core tracker checked 2026-07-21 — no issue for `multiple_of=0`, a validation divide/remainder-by-zero, or this panic). The maintainers treat Python-reachable Rust panics as bugs to fix gracefully — see `../../pydantic-core/notes/prior-art.md` (#1516).
