# Excluded: the `PyStackRef_BoolCheck` assertion is a CPython bug, not solders

~107 crash dirs across the fleets are labelled `assertion` / `cpu_load-assertion`. These are **not**
a solders finding — they are a **CPython** debug-build assertion, incidentally hit while fuzzing
solders on a debug interpreter:

```
python: Python/generated_cases.c.h:10193: PyObject *_PyEval_EvalFrameDefault(...):
        Assertion `PyStackRef_BoolCheck(cond)' failed.
```

(SIGABRT, surfaced as `AddressSanitizer: ABRT` because the target build is ASan-instrumented.) It
fires in the CPython bytecode eval loop, not in solders' Rust code — the preceding fuzzer op is a
plain interpreter operation (e.g. `<module>.__annotate__()`), and it reproduces independently of
solders.

**This is filed upstream: [python/cpython#153354](https://github.com/python/cpython/issues/153354).**
It is tracked there, not here. A debug-only CPython assertion is out of scope for an *extension*
findings catalog; recorded only so the `assertion` bucket isn't mistaken for a solders crash.

Takeaway for future extension fleets on a **debug** CPython: expect a background rate of CPython's
own debug assertions in the crash pile — triage them against known CPython issues (like this one)
before attributing to the extension.
