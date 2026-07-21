"""
EXCLUDED (known PyO3 behaviour, not a tokenizers/PyO3 bug) -- see
`../notes/excluded-pyo3-dict-iter-race.md`.

Deterministic repro of the free-threaded "dictionary changed size during iteration"
PanicException at pyo3-0.29.0/src/types/dict.rs:578, reached through
tokenizers.models.BPE(vocab=<dict>):

  BPE.__new__ takes `vocab: Option<PyVocab>` (PyVocab::Vocab(HashMap<String,u32>)) and PyO3
  extracts it into a Rust HashMap during argument parsing -- which ITERATES the passed dict via
  pyo3::types::dict::BoundDictIterator. On the free-threaded build the iterator holds only a
  per-`next()` critical section (PyO3 #4439 / #4571 -- "pyo3 follows Python's behaviour for
  multithreaded dict/list iteration and allows race conditions"), so another thread mutating that
  SAME dict changes its size between iterations and PyO3's CPython-parity check panics. The panic
  is caught by the FFI trampoline and raised as pyo3_runtime.PanicException IN the calling thread
  (the process does NOT abort; no memory unsafety).

Verdict: caller-side data race + documented PyO3 semantics. NOT filed upstream. The value is the
tooling signal -- fusil's --tsan-mutate-state reaches the PyO3 argument-extraction layer.

Run (free-threaded CPython, e.g. the fleet's TSan build or any --disable-gil interpreter with
tokenizers installed):

    PYTHON_GIL=0 <ft-python> excluded_pyo3_dict_iter_race.py   # -> PanicException on the first run
    PYTHON_GIL=1 <ft-python> excluded_pyo3_dict_iter_race.py   # -> clean (single-thread semantics)

The panic is an unconditional panic! (dict.rs:576), so it is release-affected, not debug-only.
"""
import sys
import threading

from tokenizers.models import BPE

vocab = {str(i): i for i in range(2000)}      # the shared dict: extracted AND mutated
merges = []
N_EXTRACT, N_MUTATE, ROUNDS = 4, 4, 4000
barrier = threading.Barrier(N_EXTRACT + N_MUTATE)


def extractor():
    barrier.wait()
    for _ in range(ROUNDS):
        try:
            BPE(vocab=vocab, merges=merges)   # extracts vocab -> HashMap<String,u32> (iterates dict)
        except ValueError:
            pass                              # tokenizers' own arg validation -- irrelevant here


def mutator():
    barrier.wait()
    for i in range(ROUNDS * 50):
        vocab["x%d" % (i % 64)] = i           # grow ...
        vocab.pop("x%d" % (i % 64), None)     # ... and shrink: churn the dict's size


threads = [threading.Thread(target=extractor) for _ in range(N_EXTRACT)]
threads += [threading.Thread(target=mutator) for _ in range(N_MUTATE)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print("completed cleanly (no panic this run)", file=sys.stderr)
