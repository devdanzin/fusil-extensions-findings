# SOLDERS-0002: solders.rpc.responses.batch_to_json(seq) treats each element of `seq` as an RPC
# response to serialize, but internally deserializes it as a JSON map and .unwrap()s the serde
# error. A non-empty iterable whose elements are not response maps (e.g. an int, or a byte) makes
# the deserialize fail with "invalid type: integer N, expected a map" -> panic at
# crates/rpc-responses/src/lib.rs:2044 -> pyo3_runtime.PanicException, instead of a clean
# TypeError/ValueError.
#
# Deterministic. batch_to_json([]) and batch_to_json(b"") are fine (no elements); batch_to_json("a")
# raises a proper TypeError. The panic needs a non-empty iterable with a non-response element.
from solders.rpc.responses import batch_to_json

batch_to_json([0])  # element 0 -> "invalid type: integer `0`, expected a map"
# batch_to_json(b"a")  # equivalent: bytes iterate to ints; 0x61 == 97 -> "integer `97`, expected a map"
