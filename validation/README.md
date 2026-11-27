# Validation

The scripts that check the package against its archives, what their run reached, how to run them, and their logs.

| Script | What it does |
|---|---|
| `check_archives.py` | Checks the four zips against `SHA256SUMS`, extracts them into one folder and checks every file against the manifest of its archive, and that the license files at the root, outside the manifests, are the same where two zips carry one |
| `run_analysis.py` | Runs the analysis scripts in order on a copy of the extracted archives, and compares each output with the archived file of the same path: by SHA-256, then by content (CSV cell by cell, JSON key by key, text line by line) |
| `classify_differences.py` | Sorts the outputs that `run_analysis.py` found different by what explains the difference (Section "Level 1" below) |
| `compare_sbcr.py` | Compares a rerun of SBCR's tuning or evaluation with the stored run: status, similarity, fitness and candidates |
| `mergegen_sample.py` | Regenerates MergeGen's candidates of a few test conflicts with the checkpoints of the models archive and compares them with the stored candidates |
| `check_prompts.py` | Renders the published prompts and compares their SHA-256 with the run records of the RQ4 archive |
| `manifest.py` | Writes and checks SHA-256 manifests of a folder |

## What was validated

The validation ran on 2026-11-23 on the machine of the study, from the four zips as they go to FigShare, with the code of this repository. It has three levels, and none of them covers the preparation of the data from the sources of the datasets (`preparation/`: the trace of Dataset1 from its FigShare item, the combination filter, the splits, the data of each root and the dates of the merge commits from the GitHub API). The archives hold the outputs of the preparation, and the analyses start from them.

**The environment and the archives.** The image of `environments/` was built from its Dockerfile without cache, and `check_image.sh` found the packages of its three environments equal to their locks. The five tests pass in it, and `--help` runs for every script but the four files of `mergegen/` derived from the original MergeGen code. The four zips match `SHA256SUMS`, and each of the 403,030 extracted files matches the manifest of its archive, with no file outside a manifest.

**Level 1, the analysis.** Every analysis script that reads the archives ran in the image, in the order of the study, on a copy of the extracted archives, and each output was compared with the archived file of the same path. The similarities, the comparisons of RQ1 to RQ3 and their spread across splits and seeds, the leakage and project-disjoint comparisons, the population counts, times and partition sizes, the RQ3 statistics, the chronological effects, the resolution categories of Dataset2, the overlap between the datasets, the consistency checks, the decoding of MergeGen's candidates, the RQ4 draw, packages, frame at scale and join, the origin of SBCR's candidates and the two figures give the archived files byte for byte, or differ from them only in what the class of each difference explains: paths, elapsed times, the alignment and order of rows that the English names change, the commit and the hashes of translated inputs that some outputs record, and the date of the run in the coding sheets of the RQ4 draws. The two figures have the bytes of the figures of the paper. The models of the characteristics associated with the winner give coefficients, fits and bootstrap intervals that differ from the archived ones by at most 1.23e-05, and no value changes at three decimals. The fits of `winner-model-three-predictors`, which ran on this machine, give the archived CSV files byte for byte. Those of `winner-model-two-predictors`, the two-predictor model and its refits with three predictors, ran in a container on another computer, and 8 of their 16 CSV files differ, by at most that amount. The logs of the fits also differ from the archived ones, in the ways `logs/level-1/numbers.md` lists. The agreement report of block 1 in the RQ4 archive is the one `kappa_report.py` writes from the published coding sheet. The outputs that print a result in place of writing a file (`cap_share.py`, `test_overlap.py`, `faster_slower_counts.py`) give the numbers of the paper. `logs/level-1/numbers.md` lists each output that differs in content.

**Level 2, SBCR.** One evaluation and one tuning, in the image, on Dataset1 of `partition-1`. The evaluation of the 549 test conflicts with the configuration of the study (3 neighbors, 10 iterations without improvement, 20 seconds) and seed 3022024 gives the stored candidates byte for byte for the first 132 conflicts, in the order of the run. The 133rd reaches the timeout of 20 seconds, in this run as in the stored one, and from there the search draws other random numbers, since one generator serves all the conflicts: 349 of the 549 candidates are identical, every status is the same, and the mean similarity is 0.7835 against 0.7872 stored. The tuning ran the 80 configurations of the grid on the first 10 conflicts of its draw: 568 of the 800 similarities are identical, and their mean is 0.7516 against 0.7522 stored. All 80 of the first conflict are identical. Two more runs of the tuning on the first two conflicts agree with each other and with the run in the image, and differ from the stored run in 4 of the 80 configurations of the second conflict, runs of under 15 milliseconds that no time limit reaches. We did not find the cause.

**Level 3, MergeGen.** `setup_env.sh` created a new environment, `mergegen-repl-check`, from its lock and ran `verify_env.py` on the five checkpoints of the models archive: each gives the reference digest of `reference_digests.json`. With the same environment, the five checkpoints regenerate the stored candidates of the first 10 test conflicts of each dataset of `partition-1`, 50 of 50. The times of the inference depend on the machine and were not compared. Training was not repeated.

**Not rerun.** `analysis/chronological/chronological_references.py`, which runs MergeGen's inference and SBCR's evaluation on the chronological split with the models and configurations of the three partitions; `analysis/rq4/annotator/run_annotator.py`, which calls the model, whose prompts `check_prompts.py` checked against every run record of the RQ4 archive (the labeling prompt of v1 against the 50 records of block 1 and the 1,979 at scale, the derivation prompt against its 2 records), and whose tests run against a stand-in for the API; the drivers of `pipeline/`; and SBCR on the other datasets.

**From a clone.** On 2026-11-25 the three levels ran again on the same machine, from a clone of this repository from GitHub and the files of the two FigShare items, each in a folder of its own, with the commands of the next section as written. The image was built the day before under another name, without cache, and `check_image.sh` found its three environments equal to their locks. The archives pass the same checks. In level 1 every step ends with exit code 0, the outputs that differ from the archived ones are those of 2026-11-23 with the same classes, and the CSV files of the winner model have the same largest differences. One output differs no more: `split-comparison/sbcr_similarities.csv`, whose rows are in another order, is now counted as equal in content. In level 2 the evaluation gives the numbers above, and the tuning gives 567 of the 800 similarities identical, with a mean of 0.7505 against 0.7522 stored. In level 3 a new environment, `mergegen-repl-clone`, gives the five reference digests and regenerates the 50 stored candidates. The logs are in `logs/clone/`.

## How to run it

On a machine with Docker, conda and an NVIDIA GPU (the study used an Intel Core i9-14900KF, 128 GB of RAM and an NVIDIA RTX 5090). Set these variables, from the root of a clone of this repository:

```bash
PKG=$PWD                           # this repository
DATA=/path/to/data                 # the files of the data item of FigShare: datasets.zip, results.zip, rq4.zip, SHA256SUMS
MODELS=/path/to/models             # the files of the models item: models.zip, SHA256SUMS
OUT=/path/to/validation            # an empty folder, where everything below is written
IMAGE=sbcr-study-analysis          # the name of the analysis image
MG_ENV=mergegen-repl               # the name of the MergeGen environment to create, which must not exist
RUN="docker run --rm --network none --user $(id -u):$(id -g) -e HOME=/tmp -v $PKG:/package:ro -w /package"
```

The image, the archives and the two inputs that are not in them: `Salesforce/codet5-small` of Hugging Face at revision `b1ee9570c289f21b5922b9c768a1ce12957bf968`, whose seven files have the bytes of the backbone the models were trained on, and the checkout of the tag `submitted-version`, which `analysis/winner/build_table.py` reads.

```bash
docker build --no-cache -t "$IMAGE" environments
mkdir -p "$OUT/logs/level-1" "$OUT/logs/level-2" "$OUT/logs/level-3" "$OUT/backbone/codet5-small-local" "$OUT/submitted"
$RUN -v "$DATA":/data:ro -v "$MODELS":/models:ro -v "$OUT":/out "$IMAGE" conda run --no-capture-output -n sbcr-analysis \
    python validation/check_archives.py --zips /data /models --out /out/archives | tee "$OUT/logs/archives.log"
cp -a "$OUT/archives" "$OUT/work"
REV=b1ee9570c289f21b5922b9c768a1ce12957bf968
for f in added_tokens.json config.json merges.txt pytorch_model.bin special_tokens_map.json tokenizer_config.json vocab.json; do
    curl -sSfL -o "$OUT/backbone/codet5-small-local/$f" "https://huggingface.co/Salesforce/codet5-small/resolve/$REV/$f"
done
(cd "$OUT/backbone/codet5-small-local" && sha256sum -c "$PKG/validation/codet5-small.sha256")
git archive submitted-version | tar -x -C "$OUT/submitted"
```

**Level 1**, the analysis, in the image with the network off. `run_analysis.py` copies the backbone into `partition-1/mergeGen/` of the work copy, where the token counts read it, and links `data/` and `mergeGen/` of `partition-1-sbcr-seeds` to `partition-1`, which that root reads. Keep the names of the mounts: `classify_differences.py` recognizes `/package`, `/archives`, `/w`, `/submitted` and `/backbone` in the paths the outputs record.

```bash
$RUN -v "$OUT/archives":/archives:ro -v "$OUT/work":/w -v "$OUT/logs/level-1":/logs \
    -v "$OUT/submitted":/submitted:ro -v "$OUT/backbone/codet5-small-local":/backbone:ro "$IMAGE" \
    conda run --no-capture-output -n sbcr-analysis python validation/run_analysis.py \
    --archives /archives --work /w --submitted /submitted --backbone /backbone --logs /logs
$RUN -v "$OUT/archives":/archives:ro -v "$OUT/work":/w:ro -v "$OUT/logs/level-1":/logs "$IMAGE" \
    conda run --no-capture-output -n sbcr-analysis python validation/classify_differences.py \
    --archives /archives --work /w --logs /logs
```

**Level 2**, SBCR, in the image: the evaluation of the configuration of the study on the test conflicts of Dataset1 of `partition-1`, and the tuning on the first 10 conflicts of its draw. SBCR's search is bounded by wall-clock time, so run it alone on the machine.

```bash
mkdir -p "$OUT/sbcr/data" "$OUT/sbcr/sbcr"
cp "$OUT/archives/partition-1/data/dataset1_mg_training.json" "$OUT/archives/partition-1/data/dataset1_mg_testing.json" "$OUT/sbcr/data/"
$RUN -v "$OUT/sbcr":/smoke -w /smoke/sbcr -e SEED=3022024 "$IMAGE" conda run --no-capture-output -n sbcr-analysis \
    python /package/sbcr/sbcr_evaluate.py dataset1_mg "3, 10, 20" eval_dataset1_mg_s3022024 > "$OUT/logs/level-2/evaluation.log" 2>&1
$RUN -v "$OUT/sbcr":/smoke -w /smoke/sbcr -e NUM_CHUNKS=10 "$IMAGE" conda run --no-capture-output -n sbcr-analysis \
    python /package/sbcr/sbcr_tuning.py dataset1_mg tuning_dataset1_mg > "$OUT/logs/level-2/tuning.log" 2>&1
for run in eval_dataset1_mg_s3022024 tuning_dataset1_mg; do
    $RUN -v "$OUT/archives":/archives:ro -v "$OUT/sbcr":/smoke:ro "$IMAGE" conda run --no-capture-output -n sbcr-analysis \
        python validation/compare_sbcr.py --new "/smoke/sbcr/$run" --stored "/archives/partition-1/sbcr/$run" \
        > "$OUT/logs/level-2/${run%%_dataset1*}_compare.log"
done
```

**Level 3**, MergeGen, outside the image, since it needs the GPU: the environment from its lock with the smoke test of the five checkpoints, then the candidates of the first 10 test conflicts of each dataset of `partition-1`.

```bash
bash mergegen/environment/setup_env.sh --name "$MG_ENV" --models "$OUT/archives/partition-1/mergeGen/MODELS" \
    --backbone "$OUT/backbone/codet5-small-local" 2>&1 | tee "$OUT/logs/level-3/setup_env.log"
conda run --no-capture-output -n "$MG_ENV" python validation/mergegen_sample.py --data "$OUT/archives/partition-1/data" \
    --models "$OUT/archives/partition-1/mergeGen/MODELS" --stored "$OUT/archives/partition-1/mergeGen/JIT" \
    --backbone "$OUT/backbone/codet5-small-local" --n 10 2>&1 | tee "$OUT/logs/level-3/mergegen_sample.log"
```

The validation of 2026-11-23 ran these steps on the machine of the study, from the zips copied into an empty folder, with the paths of that machine.

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
| `logs/clone/` | The three levels run from a clone with the commands above: the build of the image, `check_archives.py`, the summary, comparison, differences and step logs of level 1, the runs and comparisons of level 2, and the logs of level 3 |

## Level 1

Each output that differs from the archived file is in one of these classes:

- **paths**: the archives name the files of a run relative to the folder of the archives, and the validation ran from absolute paths;
- **elapsed times**: the minutes a step took, which the logs print;
- **spacing**: the archives translated the column names of printed tables, which moves their alignment;
- **lines in another order**, **same rows in another order**: the random split is named `random` in the package, and the scripts that sort by arm list it after `mg` and `pd`, while the archived files keep the order of the run;
- **provenance**: a JSON output that records the commit of the code, the date of the run and the SHA-256 of the script and of its inputs and outputs. The archives give no commit, and they give the hashes of the inputs as they were before the archives translated their content, so a rerun on the translated files records other hashes;
- **date of the run**: the coding sheets of the RQ4 draws carry the date the script ran;
- **content**: anything else, read one by one in `numbers.md`.
