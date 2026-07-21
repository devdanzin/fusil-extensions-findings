# PYDANTIC-0003 — a deeply nested core-schema overflows the native stack at `SchemaValidator` build (hard crash)

**Found** during design-phase probing while building the `fusil_pydantic_plugin`; reproduced by the plugin's `seed_deep_nesting` factory. pydantic_core **2.41.5**, target CPython 3.14t free-threaded + ASan.

## Reproducer

```python
from pydantic_core import SchemaValidator, core_schema as cs

schema = cs.int_schema()
for _ in range(5000):
    schema = cs.list_schema(schema)
SchemaValidator(schema)   # SIGSEGV / SIGABRT -- stack overflow (uncatchable)
```

`n=1000` builds fine; `n>=~3000` crashes. Confirmed via AddressSanitizer:

```
ERROR: AddressSanitizer: stack-overflow ...
SUMMARY: AddressSanitizer: stack-overflow ... in _pydantic_core::validators::build_validator_inner
                                                 (src/validators/mod.rs:551)
```

**This is a hard crash, not a panic** — `panic = "unwind"` cannot catch a stack overflow, so unlike PYDANTIC-0001/0002 it is a `SIGSEGV`/`SIGABRT`, not a catchable `PanicException`.

## Root cause & fix

`build_validator_inner` (`src/validators/mod.rs`) recurses on each nested child schema (the `items_schema` of `list`/`set`/`dict`, `union`/`chain` choices, `nullable`/`default` inner schema, …) with **no recursion-depth guard at construction**. pydantic-core *does* guard recursion at **validate/serialize** time — the `RecursionState` guard / `_recursion_limit` returns a clean `recursion_loop` error — but that guard is instantiated only at validate/serialize (`mod.rs:354/381/433`), **never during build**. So a schema nested a few thousand levels deep overflows the native stack while `SchemaValidator(...)`/`SchemaSerializer(...)` is still building it.

This is distinct from **cyclic** `definition-ref` schemas, which *are* guarded (they return a `RecursionError`/`recursion_loop` at validate, not a crash).

**Fix:** add a construction-time depth guard — mirror the validate-time `RecursionState`, or a simple build depth counter — that returns a `SchemaError` past a limit instead of recursing into a stack overflow.

## Prior art

Unreported (tracker checked 2026-07-21). The DoS/stack-overflow class is the only *hard* crash of the pydantic-core set; the validate-time recursion guard shows the maintainers already handle the analogous input-side case. See `../../pydantic-core/notes/prior-art.md`.
