from solders.pubkey import Pubkey

Pubkey.from_bytes(b"x")  # any bytes whose length != 32 panics; from_bytes(bytes(32)) is fine
