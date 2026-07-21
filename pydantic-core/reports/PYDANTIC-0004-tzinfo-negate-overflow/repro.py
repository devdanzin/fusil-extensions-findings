"""PYDANTIC-0004 -- pydantic_core.TzInfo(seconds) panics ("negate with overflow") on a large
negative float, instead of raising the intended ValueError.

TzInfo::py_new (src/input/datetime.rs:674) takes `seconds: f32` and does `seconds.trunc() as i32`;
a large-magnitude negative float SATURATES to i32::MIN on that cast. TryFrom<i32> then range-checks
with `if seconds.abs() >= 86400` (datetime.rs:756) -- and `i32::MIN.abs()` OVERFLOWS (|i32::MIN| =
2147483648 > i32::MAX), panicking at core/num/mod.rs:426 ("attempt to negate with overflow") BEFORE
the check can return its intended ValueError. Because py_new narrows to f32 first, any float that
narrows/casts to i32::MIN triggers it (-1e18, -inf, -2147483648.0, even -2147483647.0). pydantic-core
builds panic=unwind, so it surfaces as pyo3_runtime.PanicException.

TzInfo is public API (pydantic_core.TzInfo, in __all__). Run: python repro.py
"""
import pydantic_core as pc


def show(v):
    try:
        r = pc.TzInfo(v)
        print(f"TzInfo({v!r}) -> OK ({r!r})")
    except BaseException as e:  # noqa: BLE001
        print(f"TzInfo({v!r}) -> {type(e).__module__}.{type(e).__name__}: {str(e).splitlines()[0]}")


show(-1e18)  # saturates to i32::MIN -> PanicException
show(float("-inf"))  # saturates to i32::MIN -> PanicException
show(-2147483648.0)  # exactly i32::MIN -> PanicException
# for contrast, the intended behaviour on a merely out-of-range offset:
show(-90000.0)  # -> ValueError "TzInfo offset must be strictly between -86400 and 86400"
show(3600.0)  # -> OK
