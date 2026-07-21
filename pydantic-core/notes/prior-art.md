# Prior art (pydantic/pydantic-core, checked 2026-07-21)

`gh api search/issues` over `repo:pydantic/pydantic-core` for each finding (multiple_of=0, a
validation divide/remainder-by-zero, SchemaValidator panics on an invalid schema, a deeply-nested
schema stack overflow, uuid/custom-error/on_error panics) returned **no matching issue**. All three
findings (the five crash patterns) appear **unreported**.

## Maintainer stance: Python-reachable Rust panics are bugs

The strongest framing comes from **[#1516](https://github.com/pydantic/pydantic-core/issues/1516)**
("Rust stacktraces and panics with validate_assignment and custom fields", closed 2024-11-05). The
reporter hit a Rust panic (`model_fields.rs:422`) from a real project and argued *"I think the
correct behavior would be to fail gracefully instead of panicking."* The maintainer
(**davidhewitt**) responded *"Thanks for the report"* and engaged, asking for a minimal
reproduction. So pydantic-core does **not** treat a Python-reachable Rust panic as acceptable — the
expectation is a graceful `SchemaError`/`ValidationError`. That is exactly the bar PYDANTIC-0001/0002
miss (`PanicException` where a clean error is expected), and PYDANTIC-0003 misses harder (an
uncatchable stack overflow).

## The trust-boundary caveat (worth stating when filing)

`SchemaValidator`/`SchemaSerializer`/`core_schema` are **public** `pydantic_core` API, but in practice
most schemas come from the pydantic layer, which only ever emits *valid* schemas. A maintainer may
therefore consider a hand-built hostile schema lower-priority than #1516's real-project panic. Two
points keep these in scope:

- `SchemaValidator.__new__` **does not** validate the schema against the self-schema
  (`src/validators/mod.rs:138`) — there is no "you passed an invalid schema" guard, it goes straight
  to the builders. Tools that build custom core schemas directly (pydantic plugins, codegen, other
  libraries) are a real audience.
- The fix is uniform and cheap: **validate at build and return `SchemaError`** (PYDANTIC-0001/0002),
  or add a **construction-time depth guard** (PYDANTIC-0003). No behavior change for valid schemas.

## Per-finding

- **PYDANTIC-0001** (`multiple_of=0`): unreported. Same shape as the sibling `cryptography`
  finding CRYPTOGRAPHY-0001 (a zero divisor that should be rejected).
- **PYDANTIC-0002** (build-time `unreachable!`/`unwrap` on `custom_error_type`/`on_error`/`version`):
  unreported. Note the agent-suggested `function.type` site is **already guarded** on 2.41.5.
- **PYDANTIC-0003** (deep-nesting stack overflow at build): unreported. pydantic-core already guards
  the analogous *validate-time* recursion (`recursion_loop`), so the construction-side gap is a
  natural, consistent fix.
