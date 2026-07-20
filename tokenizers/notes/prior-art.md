# Prior art vs the tokenizers tracker (huggingface/tokenizers, checked 2026-07-20)

Searched via the GitHub search API (`gh api -X GET search/issues`) — the reliable recipe in the
top-level [`notes/searching-trackers.md`](../../notes/searching-trackers.md) (space-separated terms
= AND; `gh search --state all` is a footgun) — for the finding's function/method + the panic/overflow
class, and cross-checked with targeted `BPEDecoder` / `decode_chain` / `decoders bpe` queries.

## The class is KNOWN and the maintainers actively fix it

"A `#[pymethod]` `.unwrap()`/overflow panics → `pyo3_runtime.PanicException` on bad input" is a
recurring, acknowledged theme, and — crucially — the maintainers **fix decoder panics on hostile
input** as a matter of course:

- **PR #2154** (merged) — **"Do not panic in the Strip decoder on crafted config or short tokens."**
  Same trait method (`Decoder::decode_chain`), sibling decoder. *This is the direct precedent for
  TOKENIZERS-0001.*
- **PR #1699** (merged) — "Fix panic in `DecodeStream::step` due to incorrect index usage."
- **PR #1859** (open) — "Fix unsigned integer underflow issue with truncation." Same `usize`-underflow
  mechanism as TOKENIZERS-0001, different site.
- **#2094 [Security]** (open) / **#2198** (open) — BPE **model** `build()` process-abort / panic on a
  crafted `tokenizer.json` (merge buffer overrun) — the load-time analogue.
- Historical `PanicException` reports: #888 ("PanicException For Result::unwrap()"), #876, #821, #736,
  #444.

## Our specific site appears UNREPORTED

| finding | site | tracker status |
|---------|------|----------------|
| **TOKENIZERS-0001** | `BPEDecoder.decode([])` — `tokens.len() - 1` underflow at `decoders/bpe.rs:28` | **unreported** — none of the 6 `BPEDecoder` issues, nor any `decode_chain` / `decoders bpe` result, names the BPE decoder's empty-input underflow. #2154 is the **Strip** decoder (different file); #1859 is **truncation**; #2198/#2094 are the BPE **model** `build()`, not the BPE **decoder**. |

## Takeaway for filing

TOKENIZERS-0001 is a **new instance of a class the maintainer already recognises and has fixed for a
sibling decoder (#2154)** — a strong framing: "the same `decode_chain` short/empty-input panic as the
merged Strip-decoder fix #2154, now in `BPEDecoder`: `BPEDecoder().decode([])` underflows
`tokens.len() - 1` at `decoders/bpe.rs:28`; should return `[]`. One-line fix
(`len().saturating_sub(1)`)." Note the **debug-build-only** caveat up front (a release build doesn't
crash — the underflowed index is never read for empty input), so the report is honest about severity.
Prior art corroborates the bug and the intended fix rather than pre-empting the report.
