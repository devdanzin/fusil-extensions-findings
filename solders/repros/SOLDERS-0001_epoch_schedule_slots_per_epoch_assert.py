from solders.epoch_schedule import EpochSchedule

EpochSchedule(0)  # any slots_per_epoch < MINIMUM_SLOTS_PER_EPOCH (32) panics
