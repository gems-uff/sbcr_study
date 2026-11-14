"""Training configuration of MergeGen, in one place.

The same constants are repeated in `run_mergegen.py`, `dataset.py` and `dataset_parallel.py`.
`apply_config.py` writes them from here and checks that the three files agree.
"""

CONFIGS = {
    "original": {
        "description": (
            "Configuration of the original MergeGen study (Dong et al., ASE 2023), "
            "repository DJjjjhao/ase-merge at 0103f21."
        ),
        "backbone": "./codet5-small-local",
        "max_conflict_length": 500,
        "max_resolve_length": 200,
        "batch_size": 35,
        "test_batch_size": 30,
        "lr": 1e-4,
        "epoches": 100,
        "measured_vram_GB": 12.45,
    },
    "original_test_batch_1": {
        "description": (
            "As 'original' for training, with test_batch_size=1 at inference, so that the time "
            "written per conflict is the time of that conflict alone. The models of this study "
            "were trained with it."
        ),
        "backbone": "./codet5-small-local",
        "max_conflict_length": 500,
        "max_resolve_length": 200,
        "batch_size": 35,
        "test_batch_size": 1,
        "lr": 1e-4,
        "epoches": 100,
        "measured_vram_GB": 12.45,
    },
}

# Where each constant appears; apply_config.py reads this map.
FILES = {
    "run_mergegen.py": ["backbone", "max_conflict_length", "max_resolve_length",
                        "batch_size", "test_batch_size"],
    "dataset.py": ["backbone", "max_conflict_length", "max_resolve_length"],
    "dataset_parallel.py": ["backbone", "max_conflict_length", "max_resolve_length"],
}
