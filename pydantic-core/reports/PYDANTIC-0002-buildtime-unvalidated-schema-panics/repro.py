"""PYDANTIC-0002 -- SchemaValidator(...) panics at BUILD on invalid schema-field values.

SchemaValidator(schema) does NOT validate `schema` against pydantic-core's self-schema (it calls
build_validator directly), so a hand-built dict reaches the Rust builders unfiltered. Several
builders `unreachable!()`/`.unwrap()` on a field the self-schema would have rejected, turning an
invalid schema into a pyo3_runtime.PanicException instead of a clean SchemaError. Three examples of
the same root cause:

  custom-error without custom_error_type  -> Option::unwrap() on None  (src/validators/custom_error.rs:77)
  default with an invalid on_error        -> unreachable!()            (src/validators/with_default.rs:125)
  uuid with an out-of-set version         -> unreachable!()            (src/validators/uuid.rs:67)

Run: python repro.py   (any interpreter with pydantic_core).
"""
from pydantic_core import SchemaValidator, core_schema as cs


def show(label, schema):
    try:
        SchemaValidator(schema)
        print(f"{label}: NO panic (built OK)")
    except BaseException as e:  # noqa: BLE001
        print(f"{label}: {type(e).__module__}.{type(e).__name__}: {str(e).splitlines()[0]}")


show("custom-error w/o custom_error_type", {"type": "custom-error", "schema": cs.int_schema()})
show("default on_error='banana'", {"type": "default", "schema": cs.int_schema(), "on_error": "banana"})
show("uuid version=2", cs.uuid_schema(version=2))
show("uuid version=0", cs.uuid_schema(version=0))
show("uuid version=9", cs.uuid_schema(version=9))
