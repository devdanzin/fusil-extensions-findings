# pydantic-core fuzzing environment & how to reproduce

## Paths (host: the fusil dev box)

- **Venv (target + runner):** `/home/danzin/projects/labeille/venvs/asan-pydantic-core/bin/python`
  — CPython **3.14t free-threaded + AddressSanitizer** (`--disable-gil`), GIL off. Has
  **pydantic_core 2.41.5** (editable, src `/home/danzin/projects/laruche/repositories/pydantic-core`)
  + fusil + python-ptrace + the `fusil_pydantic_plugin` (editable). **No pydantic** (nor
  `annotated_types`/`typing_inspection`), so the plugin's optional pydantic-schema harvest is inert
  here — install it with `pip install --no-deps pydantic` if wanted (never plain `pip install
  pydantic`: it would replace the instrumented editable `pydantic_core` with a released wheel).
- **TSan venv:** `/home/danzin/projects/labeille/venvs/tsan-pydantic-core/bin/python` — CPython 3.14t
  FT + ThreadSanitizer, pydantic_core 2.41.5 (TSan-built `.so`). For `--tsan` (free-threading
  data-race) runs.
- **pydantic-core Rust source:** `/home/danzin/projects/laruche/repositories/pydantic-core` — the
  PyO3 crate is `src/` (panic sites: `src/input/return_enums.rs`, `src/validators/{custom_error,
  with_default,uuid,mod}.rs`); the Python API is `python/pydantic_core/` (`core_schema.py`,
  `_pydantic_core.pyi`). Build profile is `panic = "unwind"` (default), so panics are catchable
  `pyo3_runtime.PanicException`; a stack overflow is a hard `SIGSEGV`/`SIGABRT`.

## Reproduce the findings

```bash
PY=/home/danzin/projects/labeille/venvs/asan-pydantic-core/bin/python
env PYTHON_GIL=1 DEBUGINFOD_URLS= ASAN_OPTIONS=detect_leaks=0:handle_abort=1 \
    "$PY" reports/PYDANTIC-0001-int-multiple-of-zero/repro.py
env PYTHON_GIL=1 DEBUGINFOD_URLS= ASAN_OPTIONS=detect_leaks=0:handle_abort=1 \
    "$PY" reports/PYDANTIC-0002-buildtime-unvalidated-schema-panics/repro.py
env PYTHON_GIL=1 DEBUGINFOD_URLS= ASAN_OPTIONS=detect_leaks=0:handle_abort=1 \
    "$PY" reports/PYDANTIC-0003-deep-schema-stack-overflow/repro.py 5000   # exits nonzero (crash)
```

(The ASan build imports slowly ~1-2 min and prints a leak report at exit; `ASAN_OPTIONS=detect_leaks=0`
and filtering stdout by a marker keeps output readable when scripting.)

## How they were found

Surfaced during **design-phase probing** while building `fusil_pydantic_plugin` (a fusil plugin that
builds `SchemaValidator`/`SchemaSerializer` from hostile `core_schema` dicts). The plugin's seed
factories re-trigger each one; a fleet has **not** run yet (this catalog was minted from the
design-probe confirmations). The crux is that `SchemaValidator.__new__` does not self-validate the
schema, so hostile hand-built dicts reach the Rust builders unfiltered, and the construction path has
no recursion-depth guard.
