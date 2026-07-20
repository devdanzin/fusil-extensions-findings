# SOLDERS-0002 has no minimal 1-liner yet -- it is reached by the fusil --new-uninit region
# (T.__new__(T) on solders.rpc.responses types, then poking their methods). The class is a
# serde_json deserialize `.unwrap()` at crates/rpc-responses/src/lib.rs:2044 that panics when a
# JSON value that is not a map/object (e.g. a bare integer) reaches a map-expecting deserialize.
# Vehicle (reproduces the crates/rpc-responses/src/lib.rs:2044 panic 2/2):
#   /home/fusil/runs/fusil-solders_02/inst-*/python/solders_rpc_responses-panicked-*/source.py
#
# `parse_websocket_message` / `parse_notification` / `_batch_from_json` and every `*Resp.from_json`
# tested with a bare-integer JSON return a *clean* error, so the offending path is a different,
# not-yet-pinned deserialize site behind the uninitialized-object poke -- documented as a class.
import solders.rpc.responses  # see notes; minimal direct trigger pending
