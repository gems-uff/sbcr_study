#!/usr/bin/env python3
"""Token counts of the test population against MergeGen's limits.

For each dataset and arm (`mg`, the main design, and `pd`), over the test partition of the arm:

- tokenizes the input as `dataset_parallel.Dataset.git_merge` builds it (same `git merge-file
  --diff3`, same `<lbra>`/sep/`<rbra>` tokens, bos and eos included), to count the conflicts
  above 500 tokens, `max_conflict_length`;
- tokenizes the developer's whole resolution (bos and eos included) to count those above 200
  tokens, `max_resolve_length`;
- tokenizes MergeGen's candidate (`mergeGen/JIT/<dataset>_<arm>/model_*/candidates.json`): a
  candidate is truncated when its tokens reach the generation ceiling, `max_new_tokens = 2 *
  max_resolve_length = 400`, since `generate` stops either at eos or at that ceiling. An empty
  candidate does not enter this criterion (`population_candidates.py` counts it).

Runs in the `mergegen-train` environment, which has CodeT5's tokenizer.

Input: the root (`--root`), with `mergeGen/codet5-small-local`.
Output: `population_tokens.csv` in the root, or `--out`; one row per arm and test conflict.

    python analysis/datasets/population_tokens.py --root <root> [--arms mg] [--out <csv>]
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

import pandas as pd

DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
ARMS = ["mg", "pd"]
MAX_CONFLICT_LENGTH = 500
MAX_RESOLVE_LENGTH = 200
MAX_NEW_TOKENS = 2 * MAX_RESOLVE_LENGTH  # generation ceiling of jit_inference.py


def git_merge_tokens(tokenizer, lbra, rbra, tokens_base, tokens_a, tokens_b):
    """Same sequence as `mergegen_inference.MergeInference._git_merge_single`."""
    temp_dir = os.path.join(tempfile.gettempdir(), f"population-{uuid.uuid4()}")
    os.makedirs(temp_dir, exist_ok=True)
    try:
        with open(os.path.join(temp_dir, "base"), "w", encoding="utf-8") as f:
            f.write("\n".join(tokens_base))
        with open(os.path.join(temp_dir, "a"), "w", encoding="utf-8") as f:
            f.write("\n".join(tokens_a))
        with open(os.path.join(temp_dir, "b"), "w", encoding="utf-8") as f:
            f.write("\n".join(tokens_b))
        merge_file_path = os.path.join(temp_dir, "merge")
        cmd = (f'git merge-file -L a -L base -L b {os.path.join(temp_dir, "a")} '
               f'{os.path.join(temp_dir, "base")} {os.path.join(temp_dir, "b")} '
               f'--diff3 -p > {merge_file_path}')
        subprocess.run(cmd, shell=True, check=False)
        with open(merge_file_path, "r", encoding="utf-8") as f:
            merge_res = [x.strip() for x in f.readlines() if x.strip()]

        format_ids = [k for k, x in enumerate(merge_res)
                      if x in ["<<<<<<< a", ">>>>>>> b", "||||||| base", "======="]]
        final_tokens = []
        start = 0
        for k in range(0, len(format_ids), 4):
            context_tokens = merge_res[start:format_ids[k]]
            a_tokens = merge_res[format_ids[k] + 1:format_ids[k + 1]]
            base_tokens = merge_res[format_ids[k + 1] + 1:format_ids[k + 2]]
            b_tokens = merge_res[format_ids[k + 2] + 1:format_ids[k + 3]]
            start = format_ids[k + 3] + 1
            final_tokens.extend(context_tokens)
            final_tokens.append(lbra)
            final_tokens.extend(a_tokens)
            final_tokens.append(tokenizer.sep_token)
            final_tokens.extend(base_tokens)
            final_tokens.append(tokenizer.sep_token)
            final_tokens.extend(b_tokens)
            final_tokens.append(rbra)
        if start < len(merge_res):
            final_tokens.extend(merge_res[start:])
        return [tokenizer.bos_token] + final_tokens + [tokenizer.eos_token]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="experiment root")
    p.add_argument("--arms", default=",".join(ARMS), help="arms to count, comma-separated (default: mg,pd)")
    p.add_argument("--out", help="output CSV (default: population_tokens.csv in the root)")
    args = p.parse_args()
    root = os.path.abspath(os.path.expanduser(args.root))
    out = os.path.abspath(os.path.expanduser(args.out)) if args.out else os.path.join(root, "population_tokens.csv")
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in arms if a not in ARMS]
    if unknown or not arms:
        raise SystemExit(f"unknown arms {unknown}; choose among {ARMS}")

    mergegen = os.path.join(root, "mergeGen")
    os.chdir(mergegen)
    sys.path.insert(0, mergegen)
    from transformers import RobertaTokenizer

    tok = RobertaTokenizer.from_pretrained("./codet5-small-local")
    tok.add_tokens(["<lbra>", "<mbra>", "<rbra>"])
    lbra, rbra = "<lbra>", "<rbra>"

    rows = []
    for name in DATASETS:
        data = json.load(open(f"../data/{name}.json"))
        idx = {str(c): i for i, c in enumerate(data["chunk_id"])}
        for arm in arms:
            assignment = pd.read_csv(f"../splits/{arm}/{name}.csv", dtype={"chunk_id": str})
            test = list(assignment[assignment.partition == "test"].chunk_id)

            cand_paths = glob.glob(f"JIT/{name}_{arm}/model_{name}_{arm}/candidates.json")
            if not cand_paths:
                print(f"  warning: no candidates.json for {name}/{arm}, "
                      f"the candidate columns stay empty for this cell", flush=True)
            candidates = json.load(open(cand_paths[0])) if cand_paths else {}

            for k, chunk in enumerate(test):
                i = idx[chunk]
                base = " ".join(str(data["all_raw_base"][i] or "").split())
                v1 = " ".join(str(data["all_raw_a"][i] or "").split())
                v2 = " ".join(str(data["all_raw_b"][i] or "").split())
                res = " ".join(str(data["all_raw_res"][i] or "").split())

                tokens_base = tok.tokenize(base)
                tokens_a = tok.tokenize(v1)
                tokens_b = tok.tokenize(v2)
                merged = git_merge_tokens(tok, lbra, rbra, tokens_base, tokens_a, tokens_b)
                input_tokens = len(merged)

                resolution_tokens = len(tok.tokenize(res)) + 2  # bos + eos, as in truncated_references.py

                cand = candidates.get(chunk)
                cand_empty = cand is not None and str(cand).strip() == ""
                cand_tokens = len(tok.tokenize(" ".join(str(cand or "").split()))) if cand is not None else None

                rows.append({
                    "dataset": name, "arm": arm, "chunk_id": chunk,
                    "input_tokens": input_tokens, "input_above_500": input_tokens > MAX_CONFLICT_LENGTH,
                    "resolution_tokens": resolution_tokens, "resolution_above_200": resolution_tokens > MAX_RESOLVE_LENGTH,
                    "candidate_mergegen_empty": cand_empty,
                    "candidate_mergegen_tokens": cand_tokens,
                    "candidate_mergegen_truncated": (cand_tokens is not None and not cand_empty
                                                     and cand_tokens >= MAX_NEW_TOKENS),
                })
                if (k + 1) % 200 == 0:
                    print(f"  {name}/{arm}: {k+1}/{len(test)}", flush=True)
            print(f"{name}/{arm}: {len(test)} test conflicts processed", flush=True)

    t = pd.DataFrame(rows)
    t.to_csv(out, index=False)
    print(f"\nwritten: {len(t):,} rows in {out}")


if __name__ == "__main__":
    main()
