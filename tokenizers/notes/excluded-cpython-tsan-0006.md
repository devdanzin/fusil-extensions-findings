# Excluded: the ~686 segfaults are a CPython free-threading race, not tokenizers

Of the ~727 crash dirs in `fusil-tokenizers_01`, **686 are AddressSanitizer reports** (675 `SEGV` +
11 `ABRT`) and only 41 are the tokenizers panic (TOKENIZERS-0001). The 686 are **not** a tokenizers
finding — they are a **CPython** free-threading data race, hit incidentally because the fleet runs
`--concurrency-stress` on a **free-threaded + ASan + debug** interpreter. This note records the
evidence so the SEGV pile isn't mistaken for a tokenizers crash.

## The dominant race: `itertools.count` concurrent `repr()` → UAF in `PyObject_Repr`

The truncated fleet stdout only shows `AddressSanitizer: SEGV on unknown address` with **no stack**
(fusil kills the child on the first `AddressSanitizer` match, before the symbolized report flushes),
so the SEGVs were resolved by re-running the crashing `source.py` under **gdb** (`handle_segv=0` so
gdb catches the raw fault). A sample of **32 crash dirs spanning all 16 module-label families across
2 instances** was reproduced:

- **32/32 crashed**; **32/32 in pure CPython frames; 0/32 in tokenizers / Rust / the `.so`.**
- 29/32 fault at `PyObject_Repr` (`Objects/object.c:764`, dereferencing `Py_TYPE(v)` on a stale
  pointer) reached via `PyUnicode_FromFormat("%s(%R, %R)", ...)` — the repr of a shared
  `itertools.count(start, step)`; the other 3/32 fault one frame earlier in
  `long_to_decimal_string_internal` stringifying the count's concurrently-freed long. Same race.
- A sibling frame carries `arg=0x7970677562656478` (the ASCII bytes `"xdebugpy"`) — an object
  pointer overwritten by string data: textbook memory corruption from a data race.

This is **TSAN-0006** in the sibling
[`cpython-tsan-findings`](https://github.com/devdanzin/cpython-tsan-findings) catalog — *"itertools:
concurrent `repr()` of a shared `count()` races `count_repr`'s plain read of `lz->cnt` against
`count_next`'s atomic advance"* — whose signature list explicitly includes `SEGV
Objects/object.c:PyObject_Repr`. It is filed upstream:

- **[python/cpython#153908](https://github.com/python/cpython/issues/153908)** (closed/fixed) — the
  `count.__repr__` plain-read race. The fleet build (`3.14:07efb08`, Jul 4 2026) predates or didn't
  backport the fix, so it still reproduces.
- **[python/cpython#153981](https://github.com/python/cpython/issues/153981)** (open) — the
  counting-slow-mode UAF (the big-int `count(%R, %R)` path these backtraces hit).
- Umbrella **[python/cpython#153852](https://github.com/python/cpython/issues/153852)** (open).

Why tokenizers is blameless: fusil's stress region shares a fixed set of **generic** Python objects
and iterators (`str/bytes/list/tuple/dict/range/itertools.count/struct.iter_unpack`) and calls
`repr()` on them from 4 worker threads under `PYTHON_GIL=0`. The `itertools.count` in that set races
in CPython's own C before anything reaches tokenizers — even in the dirs that also share
`Tokenizer`/`Encoding` instances.

## Secondary: a CPython generator assertion

~11 `ABRT` / 2 `-assertion` dirs are a CPython debug assertion, not tokenizers:

```
Objects/genobject.c:261: gen_send_ex2: Assertion `gen->gi_exc_state.previous_item == NULL' failed.
```

A generator exception-state corruption under free-threading (SIGABRT via `abort_on_error=1`). Not in
the TSan catalog and distinct from TSAN-0036 (a different `genobject.c` line); it fits the open
CPython class **[python/cpython#120321](https://github.com/python/cpython/issues/120321)** ("SIGSEGV
with generators in free-threaded build"). Tracked upstream, out of scope for a tokenizers catalog.

## Takeaway for future extension fleets on a free-threaded / debug CPython

Expect the crash pile to be **dominated by CPython's own free-threading races** (repr-of-shared-object
UAFs, generator/state asserts), not the extension. Because the truncated ASan stdout can't be
deduped by regex (every SEGV reads identically), you must **gdb-resolve a sample** to attribute them.
To actually mine the *extension*, use a single-threaded fleet, or unmask concurrency by targeting a
CPython build with cpython#153908 fixed (or drop `itertools.count` from fusil's shared-iterator set /
add a TSAN-0006 suppression) so the CPython noise stops firing first.
