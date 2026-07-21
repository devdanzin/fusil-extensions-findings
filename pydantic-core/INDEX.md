# pydantic-core — findings index

[**pydantic-core**](https://github.com/pydantic/pydantic-core) is the Rust/[PyO3](https://pyo3.rs)
validation & serialization engine underneath [pydantic](https://docs.pydantic.dev/). fusil fuzzes it
via the [`fusil_pydantic_plugin`](https://github.com/devdanzin/fusil_pydantic_plugin): build
`SchemaValidator`/`SchemaSerializer` from **hostile `core_schema` dicts** and drive them with
adversarial inputs.

## Why it works

`pydantic_core.SchemaValidator(schema)` **does not validate `schema` against the self-schema** (it
calls `build_validator` directly, `src/validators/mod.rs:138`), so a hand-built dict reaches the Rust
builders unfiltered. Builders that assume the pydantic layer pre-validated the schema `unreachable!()`/
`.unwrap()` on invalid fields, and the construction path has **no recursion-depth guard**. pydantic-core
builds `panic = "unwind"`, so most panics surface as a catchable `pyo3_runtime.PanicException`; a stack
overflow is a hard `SIGSEGV`/`SIGABRT`.

## Environment

- **Target / runner Python:** `/home/danzin/projects/labeille/venvs/asan-pydantic-core/bin/python`
  — CPython **3.14t free-threaded + ASan**, pydantic_core **2.41.5** (editable). TSan venv:
  `tsan-pydantic-core` (for `--tsan`). Full detail: `notes/environment.md`.

## Findings (4 IDs covering 6 crash patterns)

| id | site(s) | reason | repro |
|----|---------|--------|-------|
| **PYDANTIC-0001** | `input/return_enums.rs:701`; `num-bigint-0.4.6/.../division.rs:112` | `multiple_of=0` → remainder/divide by zero at validation | `SchemaValidator(cs.int_schema(multiple_of=0)).validate_python(10)` |
| **PYDANTIC-0002** | `validators/custom_error.rs:77`; `with_default.rs:125`; `uuid.rs:67` | build-time `unwrap`/`unreachable!` on invalid schema-field values (missing `custom_error_type`; bad `on_error`; bad uuid `version`) | `SchemaValidator(cs.uuid_schema(version=2))` |
| **PYDANTIC-0003** | `validators/mod.rs:551` (`build_validator_inner`) | deeply nested schema → **hard stack overflow** at build (no depth guard) | `SchemaValidator(<5000-deep list_schema>)` |
| **PYDANTIC-0004** | `input/datetime.rs:756` (`i32::MIN.abs()`) | `TzInfo(seconds)` panics ("negate with overflow") on a large negative float that saturates to `i32::MIN`, instead of raising `ValueError` | `pydantic_core.TzInfo(-1e18)` |

PYDANTIC-0001/0002 are **PyO3 panic-on-bad-input** caught as `pyo3_runtime.PanicException` where a
`SchemaError`/`ValidationError` is expected (see `../README.md#the-dominant-bug-class-pyo3-extensions`).
PYDANTIC-0003 is a DoS-class **hard crash** (uncatchable). All reachable via the **public**
`SchemaValidator`/`core_schema` API; deterministic; build-independent (0001/0002 are ordinary
`unwrap`/`÷0`, not debug-only overflow checks).

## Status

PYDANTIC-0001/0002/0003 were minted from **design-phase probing**; a first asan fleet (`_01`/`_02`,
seeds-on) re-confirmed all three at scale (2130 crashes, 100% known). **PYDANTIC-0004 is the first
NOVEL find from an EXPLORATION fleet** (`fusil-pydantic_core_03`, plugin default: seeds off +
known-crash suppression on) — 255 dirs, all the `TzInfo` negate-overflow — proving the exploration
mode surfaces new bugs once the known ones are suppressed. Prior art all unreported; the maintainer
treats Python-reachable Rust panics as bugs to fix gracefully (`notes/prior-art.md`, #1516). **Next:**
keep exploration fleets running (+ a tsan fleet for FT races) to surface more, then (maintainer's
call) file with pydantic/pydantic-core,
framed as "panic-should-be-graceful" per #1516. The `--tsan` run already surfaces races with
`_pydantic_core::serializers` frames (`to_jsonable_python`/`infer_to_python`) — likely shared-object
(CPython) races reached *through* the serializer rather than pydantic-core's own state
(`SchemaValidator` is frozen), pending fleet triage.
