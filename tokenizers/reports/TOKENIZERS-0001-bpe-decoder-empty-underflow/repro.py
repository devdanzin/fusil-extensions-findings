from tokenizers.decoders import BPEDecoder

BPEDecoder().decode([])  # empty token list -> usize underflow at decoders/bpe.rs:28 (debug/overflow-checks build)
