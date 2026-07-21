# PYDANTIC-0004 — `TzInfo(seconds)` panics ("negate with overflow") on a large negative float, instead of raising `ValueError`

**Found** by `fusil_pydantic_plugin` in **exploration mode** (seeds off + known-crash suppression on) — fleet `fusil-pydantic_core_03`, **255 crash dirs, all this one panic**: the first *novel* finding once the known PYDANTIC-0001/0002/0003 were suppressed. pydantic_core **2.41.5**.

## Reproducer

```python
import pydantic_core
pydantic_core.TzInfo(-1e18)   # -> pyo3_runtime.PanicException: attempt to negate with overflow
```

`TzInfo` is public API (`pydantic_core.TzInfo`, in `__all__`). Boundary:

| call | result |
|------|--------|
| `TzInfo(-1e18)`, `TzInfo(float('-inf'))`, `TzInfo(-2147483648.0)`, `TzInfo(-2147483647.0)` | `PanicException: attempt to negate with overflow` |
| `TzInfo(-90000.0)` (out of range, but not `i32::MIN`) | `ValueError: TzInfo offset must be strictly between -86400 and 86400` ✅ |
| `TzInfo(3600.0)` | `TzInfo(3600)` ✅ |
| `TzInfo(float('nan'))` | `TzInfo(0)` (NaN casts to 0) |

## Root cause & fix

```rust
// src/input/datetime.rs
#[pyo3(signature = (seconds = 0.0))]
fn py_new(seconds: f32) -> PyResult<Self> {
    Self::try_from(seconds.trunc() as i32)          // :674  float -> i32 SATURATES
}

impl TryFrom<i32> for TzInfo {
    fn try_from(seconds: i32) -> PyResult<Self> {
        if seconds.abs() >= 86400 {                 // :756  i32::MIN.abs() OVERFLOWS
            Err(PyValueError::new_err(format!(
                "TzInfo offset must be strictly between -86400 and 86400 (24 hours) seconds, got {seconds}"
            )))
        } else { ... }
    }
}
```

Rust's `float as i32` **saturates**, so a large-magnitude negative float becomes `i32::MIN` (`-2147483648`). `TryFrom<i32>` then range-checks with `seconds.abs()` — and `i32::MIN.abs()` overflows (|i32::MIN| = 2147483648 > `i32::MAX`), panicking in the Rust stdlib (`core/num/mod.rs:426`) reached from `datetime.rs:756`, **before** the check can return its intended `ValueError`. Because `py_new` narrows to `f32` first, the threshold is fuzzy: even `-2147483647.0` rounds to `i32::MIN` in `f32` and panics.

**Fix:** compute the magnitude without overflow — `seconds.unsigned_abs() >= 86400` (returns `u32`) — or range-check without `abs` (`!(-86400 < seconds && seconds < 86400)`), or reject the saturating/non-finite cast up front. The value is *already* out of range, so it should simply take the `Err` branch.

**Guarded twin:** the same check works for every offset except `i32::MIN` — `TzInfo(-90000.0)` returns the intended `ValueError`, and a large *positive* float saturates to `i32::MAX` (whose `abs()` is fine) and also raises `ValueError`. Only the `i32::MIN` saturation makes `abs()` overflow.

## Prior art

Unreported (pydantic/pydantic-core tracker checked 2026-07-21 — no issue for a `TzInfo` panic, a negate/overflow, or this site). See `../../pydantic-core/notes/prior-art.md` (#1516: the maintainers treat Python-reachable Rust panics as bugs to fix gracefully).
