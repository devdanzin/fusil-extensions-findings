# Prior art vs the solders tracker (kevinheavey/solders, checked 2026-07-20)

Searched via the GitHub search API (`gh api -X GET search/issues`) for each finding's
function/module + the panic class, and cross-checked against a full `gh issue/pr list` + grep.
(Re-confirmed with working search: `EpochSchedule`/`slots_per_epoch`/`batch_to_json`/
`TryFromSliceError` all return `total_count: 0`.) The search recipe — and the `--state all` footgun
that made the *first* attempt come back empty — is documented in the top-level
[`notes/searching-trackers.md`](../notes/searching-trackers.md).

## The class is KNOWN and the maintainer actively fixes it

The "PyO3 `.unwrap()` panics → `pyo3_runtime.PanicException` on bad input" class is a recurring,
acknowledged theme:

- **#122** (closed) — `Keypair.from_base58_string` on a wrong key →
  `PanicException: called Result::unwrap() on Err(signature::Error ...)`, "process is lost after this
  exception." *Same shape as all three of our findings, different function.*
- **#108** (closed) — "the rust part does not correctly handle some responses" → an uncatchable
  `PanicException`; RPC-response-related but vague (no function named).
- **#91** (closed) — "Panic output can't be prevented" (Keypair).
- **PR #93** (MERGED) — **"Avoid panic in `Keypair.from_base58_string`"** — the maintainer *fixed* one
  instance (validate → return a `PyErr` instead of `.unwrap()`), so the fix pattern is established and
  accepted.

## Our three specific sites appear UNREPORTED

None of the three functions/sites has its own issue:

| finding | site | tracker status |
|---------|------|----------------|
| **SOLDERS-0001** | `EpochSchedule(slots_per_epoch<32)` assert | **unreported** — no issue mentions EpochSchedule / slots_per_epoch (only #100 = an unrelated `rent_epoch` overflow) |
| **SOLDERS-0002** | `batch_to_json([0])` serde unwrap | **unreported** — no issue names `batch_to_json`; the closest, #108, is a vague RPC-response report (closed); #147 (open) is a parse *error*, not a panic |
| **SOLDERS-0003** | `Pubkey.from_bytes(len≠32)` unwrap | **unreported** — many Pubkey issues (#132 TypeError, #98/#78/#77/#56 import/usage) but none about `from_bytes` panicking on a wrong length |

## Takeaway for filing

All three are **new instances of a class the maintainer already recognises and has fixed once (#93)** —
a strong framing for an issue/PR: "three more `Keypair.from_base58_string`-style panics, with 1-line
repros — `EpochSchedule(0)`, `Pubkey.from_bytes(b'x')`, `batch_to_json([0])` — each should raise a
`ValueError`/`TypeError` instead of `pyo3_runtime.PanicException`." Prior art corroborates the bug and
the intended fix rather than pre-empting the report.
