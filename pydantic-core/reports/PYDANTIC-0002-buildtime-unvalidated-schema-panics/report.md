# PYDANTIC-0002 — `SchemaValidator(...)` panics at build on invalid schema-field values (instead of `SchemaError`)

**Found** while surface-mapping pydantic-core for the `fusil_pydantic_plugin`; reproduced by the plugin's `seed_custom_error_no_type` / `seed_default_bad_on_error` / `seed_uuid_bad_version` factories. pydantic_core **2.41.5**.

## Reproducer

```python
from pydantic_core import SchemaValidator, core_schema as cs

SchemaValidator({"type": "custom-error", "schema": cs.int_schema()})              # no custom_error_type
SchemaValidator({"type": "default", "schema": cs.int_schema(), "on_error": "banana"})
SchemaValidator(cs.uuid_schema(version=2))                                        # or 0, 9, ...
```

| invalid schema | panic | site |
|----------------|-------|------|
| `custom-error` without `custom_error_type` | `called Option::unwrap() on a None value` | `src/validators/custom_error.rs:77` |
| `default` with `on_error` ∉ {`raise`,`omit`,`default`} | `internal error: entered unreachable code` | `src/validators/with_default.rs:125` |
| `uuid` with `version` ∉ {1,3,4,5,6,7,8} (e.g. 0, 2, 9) | `internal error: entered unreachable code` | `src/validators/uuid.rs:67` |

**Caught as:** `pyo3_runtime.PanicException`. **Expected:** an invalid schema-field value should raise `SchemaError` at build, as most invalid fields already do.

## Root cause & fix

`SchemaValidator.__new__` **does not validate `schema` against pydantic-core's self-schema** — it calls `build_validator` directly (`src/validators/mod.rs:138`), so a hand-built dict reaches the Rust builders unfiltered. Builders that assume "the pydantic layer already validated this field" then `unwrap()`/`unreachable!()` on an invalid value:

- `CustomError::build` returns `Ok(None)` when `custom_error_type` is absent, and the caller does `.unwrap()` (`custom_error.rs:77`).
- `on_error` is matched against `"raise" | None`, `"omit"`, `"default"`, `_ => unreachable!()` (`with_default.rs:125`; the comment even says "schema validation means other values are impossible").
- `Version::from` handles `{1,3,4,5,6,7,8}` else `unreachable!()` (`uuid.rs`), and `uuid` build maps `version` through it.

`SchemaValidator`/`core_schema` is **public** `pydantic_core` API (used directly by tools building custom schemas), so these are reachable without pydantic. **Fix:** validate these fields at build and return `SchemaError` (like negative `min_length` etc.), or make the builders return an error instead of `unreachable!`/`unwrap`.

> The agent-suggested fourth site — a `function-*` schema with a bad inner `function.type` — is **already guarded** on 2.41.5 (clean `SchemaError`, not a panic). Verify statically-found panics against the built `.so`.

## Prior art

Unreported (tracker checked 2026-07-21). Maintainer stance per **#1516**: Python-reachable Rust panics are bugs to fix gracefully. See `../../pydantic-core/notes/prior-art.md`.
