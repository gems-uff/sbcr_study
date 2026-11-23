# MergeGen

Training, tokenization and just-in-time inference of MergeGen, the LLM-based approach of the study, with the configuration of the original MergeGen study (CodeT5-small, 500 conflict tokens, 200 resolution tokens, batch 35, three beams). Five files derive from the original MergeGen code and are outside the MIT license of this repository (`NOTICE.md`).

| File | What it does |
|---|---|
| `run_total_dataset.py`, `dataset_parallel.py` | Tokenize a dataset in blocks of a thousand chunks, in parallel |
| `dataset.py` | Builds the train, validation and test slices from the split of the root |
| `run_mergegen.py` | Trains a model (`python run_mergegen.py <dataset>_<arm> train`), with the seed of `TRAINING_SEED` |
| `mergegen_inference.py` | The model wrapper for one conflict at a time |
| `jit_inference.py` | Generates the candidates of the test conflicts and times each step (the candidates and times the study reports) |
| `training/configs.py`, `training/apply_config.py` | The training configuration, and a check that the three files that repeat it agree |
| `environment/setup_env.sh`, `environment/verify_env.py` | Recreate the inference environment from `environments/mergegen-repl.lock.yml` and run the smoke test |
| `setup_workdir.sh` | Links a code folder to data, backbones and output folders outside an experiment root |

The code resolves its paths relative to the working directory: `./codet5-small-local`, `PROCESSED/`, `MODELS/`, `OUTPUT/`, `AUX_FILES/` and `../data/`. `preparation/prepare_data.py` copies it into `<root>/mergeGen` and links the backbone, and the pipeline runs it from there (`pipeline/README.md`).

**Backbone.** `codet5-small-local` is a local copy of [`Salesforce/codet5-small`](https://huggingface.co/Salesforce/codet5-small). A checkpoint loads only over the backbone it was trained on.

**Non-Python dependencies.** `git`, since the structured representation runs `git merge-file --diff3` (version 2.43.0 in the study), and, for the GPU, an NVIDIA driver with CUDA 12.9 support (the torch wheel brings its CUDA libraries).

**Smoke test.** `verify_env.py` checks the versions of the pinned dependencies, the GPU and `git`, loads a checkpoint of the models archive and compares the SHA-256 of its outputs over the ten conflicts of `environment/fixtures/smoke_conflicts.json` with `environment/reference_digests.json`.

```bash
mergegen/environment/setup_env.sh --models <archives>/partition-1/mergeGen/MODELS --backbone <dir>/codet5-small-local
```

The reference digests were recorded over `Salesforce/codet5-small` at revision `b1ee9570c289f21b5922b9c768a1ce12957bf968`, whose files are the bytes of the backbone the models were trained on. `setup_env.sh` without `--models` only creates the environment, and `verify_env.py` runs on one checkpoint:

```bash
conda activate mergegen-repl
python mergegen/environment/verify_env.py --backbone <dir>/codet5-small-local \
    --checkpoint <models>/dataset2_Java_mg/best_model.pt --reference dataset2_Java_mg
```
