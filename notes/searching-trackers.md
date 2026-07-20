# Reliable issue/PR search on a project tracker (prior-art step)

Every finding needs a prior-art check against the extension's (or CPython's) tracker. `gh search`
has two footguns that silently return empty; use the **search API** and you can depend on it, even
for large repos.

## The recipe — `gh api search/issues`

```bash
R=OWNER/REPO

# count + first page (30 results) — enough to answer "is this reported?"
gh api -X GET search/issues -f q="repo:$R is:issue TERM1 TERM2" \
  --jq '.total_count, (.items[] | "#\(.number) [\(.state)] \(.title)")'

# exhaustive (large repo, >30 hits): paginate at 100/page
gh api --paginate -X GET search/issues -f per_page=100 \
  -f q="repo:$R is:issue TERM" \
  --jq '.items[] | "#\(.number) [\(.state)] \(.title)"'
```

- `-f q=...` is a form field, so spaces/quotes pass through cleanly — prefer it over hand-building
  the URL.
- A `total_count: 0` here is **trustworthy** (search ran and matched nothing).
- The API returns full item objects (`.state`, `.title`, `.body`, `.labels`, …) and `total_count`;
  `gh search` returns fewer fields.

## Query semantics (the two footguns)

1. **Space-separated terms = AND**, not a phrase. `q="Pubkey from_bytes"` finds issues containing
   **both** words (anywhere). Good for narrowing.
2. **Quotes = exact adjacent phrase.** `q='"Pubkey from_bytes"'` requires the literal string
   `Pubkey from_bytes` — almost always 0 hits. **This is the "multi-word search doesn't work" trap.**
   Only quote when you truly want a phrase.

Put every filter **inside `q`**, not as a `gh` flag:
`is:issue` / `is:pr`, `state:open` / `state:closed`, `in:title` / `in:body` / `in:comments`,
`label:X`, `author:X`, `repo:O/R`. (All validated against large + small trackers.)

## `gh search issues` (if you use it instead of the API)

- `--state` accepts **only `open` | `closed`** — **NOT `all`.** `--state all` *errors* ("invalid
  argument"), and if you pipe stdout to `jq`/`grep` you just see empty output and mistake it for "no
  results." **This was the actual bug** behind an early empty prior-art pass. Omit `--state` to get
  both states.
- Positional multi-word args are AND (fine); do **not** wrap them in quotes.

## Fallback for small repos

For a tracker with ≲100 issues, a full listing + local grep is also reliable and index-independent:

```bash
gh issue list --repo "$R" --state all --limit 300 --json number,title,state,body \
  --jq '.[] | "#\(.number) [\(.state)] \(.title)  \(.body // "" | gsub("[\\n\\r]";" ") | .[:200])"' \
  | grep -iE 'term1|term2'
```

Note `--state all` **is** valid for `gh issue list` (unlike `gh search issues`) — that inconsistency
is what caused the confusion in the first place.
