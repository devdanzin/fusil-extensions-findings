"""PYDANTIC-0003 -- a deeply nested core-schema overflows the native stack at SchemaValidator build.

build_validator_inner (src/validators/mod.rs) recurses per schema level with NO recursion-depth
guard at construction (the RecursionState guard is instantiated only at validate/serialize time).
A schema nested a few thousand levels deep therefore overflows the native stack during
SchemaValidator(...) -> SIGSEGV / SIGABRT. Unlike the panic findings this is a HARD crash: panic=
unwind cannot catch a stack overflow.

n=1000 builds fine; n>=~3000 crashes (exact threshold depends on stack size / build).

Run (each in its own process; it crashes):
    python repro.py 5000
"""
import sys

from pydantic_core import SchemaValidator, core_schema as cs

n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
schema = cs.int_schema()
for _ in range(n):
    schema = cs.list_schema(schema)
print(f"built schema nested {n} deep; calling SchemaValidator(...)", file=sys.stderr)
SchemaValidator(schema)  # SIGSEGV / SIGABRT here for large n (stack overflow, uncatchable)
print("no crash", file=sys.stderr)
