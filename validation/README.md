# Validation

The scripts that check the package against its archives, and the logs of the validation of 2026-11-23. The README of the repository says what each level reached ("What was validated").

| Script | What it does |
|---|---|
| `check_archives.py` | Checks the four zips against `SHA256SUMS`, extracts them into one folder and checks every file against the manifest of its archive |
| `run_analysis.py` | Runs the analysis scripts in order on a copy of the extracted archives, and compares each output with the archived file of the same path: by SHA-256, then by content (CSV cell by cell, JSON key by key, text line by line) |
| `classify_differences.py` | Sorts the outputs that `run_analysis.py` found different by what explains the difference (Section "Level 1" below) |
| `compare_sbcr.py` | Compares a rerun of SBCR's tuning or evaluation with the stored run: status, similarity, fitness and candidates |
| `mergegen_sample.py` | Regenerates MergeGen's candidates of a few test conflicts with the checkpoints of the models archive and compares them with the stored candidates |
| `check_prompts.py` | Renders the published prompts and compares their SHA-256 with the run records of the RQ4 archive |
| `manifest.py` | Writes and checks SHA-256 manifests of a folder |

## How the validation ran

On the machine of the study (Intel Core i9-14900KF, 128 GB of RAM, NVIDIA RTX 5090), from the zips as they go to FigShare, copied into an empty folder:

```bash
docker build --no-cache -t sbcr-study-analysis environments
python validation/check_archives.py --zips <download> --out <archives>
cp -a <archives> <work>
python validation/run_analysis.py --archives <archives> --work <work> --submitted <checkout of the submitted version> \
    --backbone <dir>/codet5-small-local --logs <logs>
python validation/classify_differences.py --archives <archives> --work <work> --logs <logs>
```

`run_analysis.py` and `check_archives.py` ran in the image, with the network off. `codet5-small-local` is `Salesforce/codet5-small` at revision `b1ee9570c289f21b5922b9c768a1ce12957bf968` of Hugging Face, whose seven files have the bytes of the backbone the models were trained on. `run_analysis.py` copies it into `partition-1/mergeGen/` of the work copy, where the token counts read it, and links `data/` and `mergeGen/` of `partition-1-sbcr-seeds` to `partition-1`, which that root reads.

## Logs

| File | What it holds |
|---|---|
| `logs/environment.log` | The checks of the image (`check_image.sh`), the five tests and `--help` of every script |
| `logs/archives.log` | `check_archives.py` |
| `logs/level-1/summary.txt` | One line per step of `run_analysis.py`: exit code and files equal, equal in content, different and not archived. "Archived files not written" counts files of the folders of a step that a later step writes; every archived file the steps cover was written by one of them |
| `logs/level-1/comparison.tsv` | Each output: step, path, result and the first differences |
| `logs/level-1/differences.tsv` | Each different output with its class from `classify_differences.py` |
| `logs/level-1/steps/` | The command and the output of each step |
| `logs/level-1/numbers.md` | The outputs the archives do not hold, checked against the paper, and the outputs checked number by number |
| `logs/level-2/` | The SBCR evaluation and tuning, and their comparison with the stored runs |
| `logs/level-3/` | `setup_env.sh` with the smoke test of the five checkpoints, and `mergegen_sample.py` |
| `logs/prompts.log` | `check_prompts.py` on the RQ4 archive |

## Level 1

Each output that differs from the archived file is in one of these classes:

- **paths**: the archives name the files of a run relative to the folder of the archives, and the validation ran from absolute paths;
- **elapsed times**: the minutes a step took, which the logs print;
- **spacing**: the archives translated the column names of printed tables, which moves their alignment;
- **lines in another order**, **same rows in another order**: the random split is named `random` in the package, and the scripts that sort by arm list it after `mg` and `pd`, while the archived files keep the order of the run;
- **provenance**: a JSON output that records the commit of the code, the date of the run and the SHA-256 of the script and of its inputs and outputs. The archives give no commit, and they give the hashes of the inputs as they were before the archives translated their content, so a rerun on the translated files records other hashes;
- **date of the run**: the coding sheets of the RQ4 draws carry the date the script ran;
- **content**: anything else, read one by one in `numbers.md`.
