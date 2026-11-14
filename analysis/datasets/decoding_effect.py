#!/usr/bin/env python3
"""Effect of decoding MergeGen's candidates to bytes, on partition 1, without changing the root.

`mergegen/jit_inference.py` builds the text of each candidate as
`''.join(tokenizer.convert_ids_to_tokens(ids)).replace('Ġ', ' ')`, as `see_results` of the
original MergeGen code does. CodeT5's tokenizer is a byte-level BPE, and that skips the mapping
of byte symbols back to bytes: ASCII text comes out right, but any other character stays as two
to four byte symbols (`Ø¨` for `ب`), while the resolutions hold the real characters. The
candidates the study reports are those stored; this script measures how much the numbers move
once they are decoded. It reads the root and writes only to `--out`. Two steps, since the
tokenizer and pylcs live in different environments:

- `decode` (environment `mergegen-train`): decodes every candidate of the seven
  `mergeGen/JIT/*_<arm>/model_*/candidates.json` files, checks each result against the
  tokenizer's `convert_tokens_to_string`, and writes the candidates whose text changes to
  `decoded_candidates.json` and the counts to `decode.json`;
- `measure` (environment `sbcr-analise`): recomputes `sim_lcs_no_whitespace` and the exact match
  of the changed candidates, after checking that the stored text reproduces the stored values,
  and runs the paired comparison, the RQ3 gaps and the MergeGen columns of
  `tabulate_population.py` on the stored and on the decoded values, checking that the stored
  run reproduces the root's `comparison.csv`, `population_candidates.csv` and
  `population_table.csv`, and `--rq3-gaps` when given.

A space in the stored text can only come from the replacement of `Ġ`, since no token of a
byte-level vocabulary holds a literal space, so putting `Ġ` back is exact.

Also a library: `corrected_mergegen` gives the decoded similarities to `analysis/winner/build_table.py`.

    conda run -n mergegen-train python analysis/datasets/decoding_effect.py decode \
        --root <root> --tokenizer <dir>/codet5-small-local --out <dir>
    conda run -n sbcr-analise python analysis/datasets/decoding_effect.py measure \
        --root <root> --out <dir> [--rq3-gaps <rq3_gaps_s3022024.csv>]
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in (HERE, os.path.join(HERE, "..", "similarity"), os.path.join(HERE, "..", "rq1_rq3")):
    sys.path.insert(0, folder)
ARM = "mg"
SEED = "3022024"
SPACE = 'Ġ'  # the space symbol of CodeT5's tokenizer, as in jit_inference.py
DECODED = "decoded_candidates.json"
TOLERANCE = 1e-12


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def commit_state():
    commit = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", HERE, "status", "--porcelain", "--", HERE],
                                capture_output=True, text=True).stdout.strip())
    return commit, dirty


def candidate_files(root):
    """The seven candidate files of the arm: the own model of each dataset and the two RQ3 crossed ones."""
    files = sorted(glob.glob(f"{root}/mergeGen/JIT/*_{ARM}/model_*/candidates.json"))
    # keys with "/" on every system, as `recompute` splits them
    return {os.path.relpath(os.path.dirname(f), f"{root}/mergeGen/JIT").replace(os.sep, "/"): f for f in files}


def decode_text(text, byte_decoder):
    """The text `convert_tokens_to_string` would have given for the tokens `build_text` joined."""
    return bytes(byte_decoder[c] for c in text.replace(' ', SPACE)).decode("utf-8", "replace")


# ---------------------------------------------------------------- decode


def run_decode(args):
    from transformers import RobertaTokenizer, __version__ as transformers_version

    root, out = args.root, args.out
    tokenizer = RobertaTokenizer.from_pretrained(args.tokenizer)
    byte_decoder = tokenizer.byte_decoder
    decoded, counts = {}, {}
    for key, path in candidate_files(root).items():
        candidates = json.load(open(path))
        changed, unknown, replaced = {}, [], []
        for chunk, text in candidates.items():
            missing = {c for c in text.replace(' ', SPACE) if c not in byte_decoder}
            if missing:
                unknown.append(chunk)
                continue
            new = decode_text(text, byte_decoder)
            if new != tokenizer.convert_tokens_to_string(list(text.replace(' ', SPACE))):
                raise SystemExit(f"{key}/{chunk}: decoding differs from convert_tokens_to_string")
            if new != text:
                changed[chunk] = new
                if '�' in new:
                    replaced.append(chunk)
        if unknown:
            raise SystemExit(f"{key}: {len(unknown)} candidates hold symbols outside byte_decoder, e.g. {unknown[:5]}")
        decoded[key] = changed
        counts[key] = {"candidates": len(candidates), "changed": len(changed),
                       "with_replacement_character": len(replaced), "replacement_chunks": sorted(replaced)}
        print(f"{key}: {len(candidates):,} candidates, {len(changed)} change, "
              f"{len(replaced)} with an invalid UTF-8 sequence", flush=True)

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, DECODED), "w", encoding="utf-8") as f:
        json.dump(decoded, f, ensure_ascii=False, indent=1, sort_keys=True)
    commit, dirty = commit_state()
    # the files the tokenizer loads, not the model weights beside them
    tokenizer_files = sorted(f for f in glob.glob(os.path.join(args.tokenizer, "*"))
                             if f.endswith((".json", ".txt")))
    meta = {"root": root, "arm": ARM, "commit": commit, "uncommitted_changes": dirty,
            "transformers": transformers_version, "tokenizer": args.tokenizer,
            "decoding": "bytes(byte_decoder[c] for c in text.replace(' ', 'Ġ')).decode('utf-8', 'replace')",
            "counts": counts,
            "inputs": {os.path.relpath(f, root).replace(os.sep, "/"): sha256(f) for f in candidate_files(root).values()},
            "tokenizer_files": {os.path.basename(f): sha256(f) for f in tokenizer_files if os.path.isfile(f)}}
    with open(os.path.join(out, "decode.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nwritten to {out}/{DECODED} and decode.json")


# ---------------------------------------------------------------- measure


def recompute(root, decoded):
    """One row per changed candidate: stored and decoded similarity and exact match.

    Stops if the stored text does not reproduce the stored values of `similarities.csv`.
    """
    import pandas as pd
    from sbcr_scores import SIM
    from sbcr_similarity import gestalt, normalize

    resolutions = {}
    rows = []
    for key, changed in decoded.items():
        folder, model = key.split("/")
        dataset = folder.rsplit("_", 1)[0]
        if dataset not in resolutions:
            d = json.load(open(f"{root}/data/{dataset}.json"))
            resolutions[dataset] = {str(c): r for c, r in zip(d["chunk_id"], d["all_raw_res"])}
        stored = json.load(open(f"{root}/mergeGen/JIT/{key}/candidates.json"))
        sim = pd.read_csv(f"{root}/mergeGen/JIT/{key}/similarities.csv", dtype={"chunk_id": str},
                          float_precision="round_trip").set_index("chunk_id")
        for chunk, new in changed.items():
            res = resolutions[dataset][chunk]
            old_sim = gestalt(normalize(stored[chunk]), normalize(res))
            old_em = float(normalize(stored[chunk]) == normalize(res))
            if abs(old_sim - sim.loc[chunk, SIM]) > TOLERANCE or old_em != sim.loc[chunk, "exact_match_full"]:
                raise SystemExit(f"{key}/{chunk}: the stored text does not reproduce similarities.csv")
            rows.append({"folder": folder, "model": model[len("model_"):].rsplit("_", 1)[0], "dataset": dataset,
                         "chunk_id": chunk, "sim_stored": old_sim,
                         "sim_decoded": gestalt(normalize(new), normalize(res)),
                         "exact_stored": old_em, "exact_decoded": float(normalize(new) == normalize(res)),
                         "replacement_character": '�' in new})
    return pd.DataFrame(rows)


def corrected_mergegen(mg, changes):
    """`load_mergegen`'s frame with the decoded similarity and exact match of the changed candidates."""
    c = changes[["dataset", "model", "chunk_id", "sim_decoded", "exact_decoded"]]
    j = mg.merge(c, on=["dataset", "model", "chunk_id"], how="left", validate="one_to_one")
    hit = j.sim_decoded.notna()
    j.loc[hit, "mergegen"] = j.loc[hit, "sim_decoded"]
    j.loc[hit, "mergegen_em"] = j.loc[hit, "exact_decoded"]
    return j.drop(columns=["sim_decoded", "exact_decoded"])


def check_comparison(root, t):
    """The stored run must give the rows of the root's `comparison.csv` exactly."""
    import pandas as pd

    c = pd.read_csv(f"{root}/comparison.csv")
    c = c[c.analysis.isin(set(t.analysis))].set_index(["analysis", "dataset", "arm"]).sort_index()
    mine = t.set_index(["analysis", "dataset", "arm"]).sort_index()[c.columns]
    if not mine.index.equals(c.index):
        raise SystemExit("the stored run does not have the rows of comparison.csv")
    worst = float((mine.select_dtypes("number") - c.select_dtypes("number")).abs().max().max())
    if worst > TOLERANCE:
        raise SystemExit(f"the stored run differs from comparison.csv by up to {worst:.3g}")
    return worst


def check_rq3_gaps(path, t):
    """The stored run must give the rows and numeric columns of the RQ3 gaps CSV."""
    import pandas as pd

    c = pd.read_csv(path).set_index(["approach", "test_set"]).sort_index()
    mine = t.set_index(["approach", "test_set"]).sort_index()
    if not mine.index.equals(c.index):
        raise SystemExit(f"the stored run does not have the rows of {path}")
    numeric = [col for col in c.columns if pd.api.types.is_numeric_dtype(c[col])
               and not pd.api.types.is_bool_dtype(c[col])]
    missing = [col for col in numeric if col not in mine.columns]
    if missing:
        raise SystemExit(f"the stored run has no columns {missing} of {path}")
    worst = float((mine[numeric] - c[numeric]).abs().max().max())
    if worst > TOLERANCE:
        raise SystemExit(f"the stored run differs from {path} by up to {worst:.3g}")
    return worst


def population(root, decoded):
    """MergeGen rows of `population_candidates.py` with the stored and the decoded text.

    The stored run must give the root's `population_candidates.csv`. Returns one row per
    candidate of the own model, with the stored and decoded exact match and V1/V2 flag.
    """
    import pandas as pd
    from population_candidates import DATASETS, load_data, made_only_of_v1v2, normalize

    published = pd.read_csv(f"{root}/population_candidates.csv", dtype={"chunk_id": str, "seed": str},
                            keep_default_na=False)
    published = published[(published.approach == "mergegen") & (published.arm == ARM)]
    rows = []
    for name in DATASETS:
        data, idx = load_data(root, name)
        key = f"{name}_{ARM}/model_{name}_{ARM}"
        candidates = json.load(open(f"{root}/mergeGen/JIT/{key}/candidates.json"))
        changed = decoded.get(key, {})
        assignment = pd.read_csv(f"{root}/splits/{ARM}/{name}.csv", dtype={"chunk_id": str})
        for c in assignment[assignment.partition == "test"].chunk_id:
            if c not in candidates:
                continue
            i = idx[c]
            v1, v2, res = data["all_raw_a"][i], data["all_raw_b"][i], data["all_raw_res"][i]
            old, new = candidates[c], changed.get(c, candidates[c])
            rows.append({"dataset": name, "chunk_id": c, "changed": c in changed,
                         "empty_stored": str(old).strip() == "", "empty_decoded": str(new).strip() == "",
                         "exact_stored": normalize(old) == normalize(res),
                         "exact_decoded": normalize(new) == normalize(res),
                         "v1v2_stored": made_only_of_v1v2(old, v1, v2),
                         "v1v2_decoded": made_only_of_v1v2(new, v1, v2)})
    p = pd.DataFrame(rows)
    j = p.merge(published, on=["dataset", "chunk_id"], how="outer", indicator=True)
    if (j._merge != "both").any():
        raise SystemExit("the stored run does not have the MergeGen rows of population_candidates.csv")
    def flag(s):
        # the empty candidates have no V1/V2 flag: None here, NaN once in a frame, "" in the CSV
        return s.map(lambda v: str(v) if str(v) in ("True", "False") else "")

    same = ((j.empty_stored.astype(str) == j["empty"].astype(str))
            & (j.exact_stored.astype(str) == j.exact_match.astype(str))
            & (flag(j.v1v2_stored) == flag(j.only_v1v2_lines)))
    if not same.all():
        raise SystemExit(f"{int((~same).sum())} MergeGen rows differ from population_candidates.csv")
    return p


def tabulate(root, p):
    """The MergeGen columns of `tabulate_population.py`, stored and decoded, per dataset and population."""
    import pandas as pd
    from sbcr_scores import sbcr_chunk_ids

    rows = []
    for name in p.dataset.unique():
        comb = sbcr_chunk_ids(root, name, ARM)
        for pop in ["test", "combination"]:
            m = p[p.dataset == name]
            if pop == "combination":
                m = m[m.chunk_id.isin(comb)]
            row = {"dataset": name, "population": pop, "n": len(m), "changed": int(m.changed.sum())}
            for state in ["stored", "decoded"]:
                full = m[~m[f"empty_{state}"]]
                row[f"mergegen_empty_{state}"] = int(m[f"empty_{state}"].sum())
                row[f"mergegen_exact_match_{state}"] = int(m[f"exact_{state}"].sum())
                row[f"mergegen_nonempty_{state}"] = len(full)
                row[f"mergegen_only_v1v2_{state}"] = int((full[f"v1v2_{state}"] == True).sum())  # noqa: E712
            rows.append(row)
    t = pd.DataFrame(rows)
    published = pd.read_csv(f"{root}/population_table.csv")
    j = t.merge(published, on=["dataset", "population"], validate="one_to_one")
    for col in ["mergegen_empty", "mergegen_exact_match", "mergegen_nonempty", "mergegen_only_v1v2"]:
        if (j[f"{col}_stored"] != j[col]).any() or len(j) != len(published):
            raise SystemExit(f"the stored run differs from population_table.csv in {col}")
    return t


def run_measure(args):
    import pandas as pd
    from compare_approaches import evaluated_sets, load_mergegen, paired_comparison, paired_frames
    from rq3_gaps import gaps, mergegen_by_model, sbcr_by_target
    from sbcr_scores import load_sbcr_similarities

    pd.set_option("display.width", 220)
    root, out = args.root, args.out
    decoded = json.load(open(os.path.join(out, DECODED), encoding="utf-8"))

    changes = recompute(root, decoded)
    changes.to_csv(os.path.join(out, "changed_candidates.csv"), index=False)
    print("=== changed candidates: stored text reproduces similarities.csv ===")
    print(changes.groupby(["folder", "model"]).agg(
        changed=("chunk_id", "size"), sim_stored=("sim_stored", "mean"), sim_decoded=("sim_decoded", "mean"),
        exact_stored=("exact_stored", "sum"), exact_decoded=("exact_decoded", "sum"),
        replacement=("replacement_character", "sum")).to_string())

    evaluated = evaluated_sets(root)
    sb = load_sbcr_similarities(root, seeds=[SEED])
    sb = sb[sb.partition == sb.arm]
    mg_stored = load_mergegen(root, evaluated)
    mg_stored = mg_stored[mg_stored.arm == ARM]
    mg_decoded = corrected_mergegen(mg_stored, changes)

    tables = {}
    for state, mg in [("stored", mg_stored), ("decoded", mg_decoded)]:
        j, j3 = paired_frames(sb[sb.arm == ARM], mg)
        tables[state] = pd.concat([paired_comparison(j, "rq1_rq2"), paired_comparison(j3, "rq3")],
                                  ignore_index=True)
        tables[state].to_csv(os.path.join(out, f"comparison_{state}.csv"), index=False)
    worst_comparison = check_comparison(root, tables["stored"])
    print(f"\nstored run matches comparison.csv, largest difference {worst_comparison:.3g}")

    # how many of the evaluated conflicts change, per analysis
    evaluated_changes = changes.merge(mg_stored[["dataset", "model", "chunk_id"]],
                                      on=["dataset", "model", "chunk_id"])
    evaluated_changes.to_csv(os.path.join(out, "changed_evaluated.csv"), index=False)

    for t in tables.values():
        # counts of conflicts, besides the shares compare_approaches.py writes
        for share in ["sbcr_wins", "tie", "mergegen_wins", "mergegen_exact"]:
            t[f"{share}_n"] = (t[share] * t.n).round().astype(int)
    cols = ["analysis", "dataset", "n", "mergegen", "mergegen_sd", "mergegen_median", "mergegen_exact",
            "mergegen_exact_n", "difference", "sbcr_wins", "sbcr_wins_n", "tie", "tie_n",
            "mergegen_wins", "mergegen_wins_n", "rank_biserial", "p"]
    both = tables["stored"][cols].merge(tables["decoded"][cols], on=["analysis", "dataset", "n"],
                                        suffixes=("_stored", "_decoded"))
    both.to_csv(os.path.join(out, "comparison_stored_vs_decoded.csv"), index=False)
    print("\n=== RQ1 to RQ3: stored vs decoded ===")
    print(both.to_string(index=False, float_format=lambda x: f"{x:.6g}"))

    gap_tables = {}
    for state, mg in [("stored", mg_stored), ("decoded", mg_decoded)]:
        gap_tables[state] = gaps(sbcr_by_target(sb, [SEED], evaluated), mergegen_by_model(mg, evaluated))
        gap_tables[state].to_csv(os.path.join(out, f"rq3_gaps_{state}.csv"), index=False)
    worst_gaps = check_rq3_gaps(args.rq3_gaps, gap_tables["stored"]) if args.rq3_gaps else None
    if worst_gaps is not None:
        print(f"\nstored run matches {args.rq3_gaps}, largest difference {worst_gaps:.3g}")
    gcols = ["approach", "test_set", "n", "own_mean", "own_median", "own_exact", "other_mean", "other_median",
             "other_exact", "gap", "ci_low", "ci_high", "own_closer", "tie", "other_closer", "rank_biserial",
             "p", "p_holm"]
    gboth = gap_tables["stored"][gcols].merge(gap_tables["decoded"][gcols], on=["approach", "test_set", "n"],
                                              suffixes=("_stored", "_decoded"))
    gboth.to_csv(os.path.join(out, "rq3_gaps_stored_vs_decoded.csv"), index=False)
    print("\n=== RQ3 gaps: stored vs decoded ===")
    print(gboth.to_string(index=False, float_format=lambda x: f"{x:.6g}"))

    p = population(root, decoded)
    p[p.changed].to_csv(os.path.join(out, "population_changed.csv"), index=False)
    t = tabulate(root, p)
    t.to_csv(os.path.join(out, "population_stored_vs_decoded.csv"), index=False)
    print("\nstored run matches population_candidates.csv and population_table.csv")
    print("\n=== population counts, MergeGen: stored vs decoded ===")
    print(t.to_string(index=False))

    commit, dirty = commit_state()
    inputs = [f"{root}/comparison.csv", f"{root}/population_candidates.csv", f"{root}/population_table.csv",
              f"{root}/sbcr_similarities.csv"]
    inputs += [f"{root}/mergeGen/JIT/{k}/{f}" for k in decoded for f in ("candidates.json", "similarities.csv")]
    inputs += sorted(glob.glob(f"{root}/data/*_{ARM}_*testing.json"))
    meta = {"root": root, "arm": ARM, "sbcr_seed": SEED, "commit": commit, "uncommitted_changes": dirty,
            "comparison_largest_difference": worst_comparison, "rq3_gaps": args.rq3_gaps,
            "rq3_gaps_largest_difference": worst_gaps,
            "inputs": {os.path.relpath(f, root).replace(os.sep, "/"): sha256(f) for f in inputs},
            "decoded_candidates": sha256(os.path.join(out, DECODED))}
    if args.rq3_gaps:
        meta["inputs_outside_root"] = {args.rq3_gaps: sha256(args.rq3_gaps)}
    with open(os.path.join(out, "measure.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nwritten to {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="step", required=True)
    d = sub.add_parser("decode", help="decode the candidates (environment mergegen-train)")
    d.add_argument("--root", required=True)
    d.add_argument("--tokenizer", required=True, help="folder of CodeT5's tokenizer")
    d.add_argument("--out", required=True)
    m = sub.add_parser("measure", help="recompute and compare (environment sbcr-analise)")
    m.add_argument("--root", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--rq3-gaps", help="rq3_gaps_s3022024.csv of rq3_gaps.py, to check the stored run against")
    args = p.parse_args()
    args.root = os.path.abspath(os.path.expanduser(args.root))
    args.out = os.path.abspath(os.path.expanduser(args.out))
    if os.path.commonpath([args.root, args.out]) == args.root:
        raise SystemExit("--out must be outside the root, which this script does not write to")
    if getattr(args, "tokenizer", None):
        args.tokenizer = os.path.abspath(os.path.expanduser(args.tokenizer))
    if getattr(args, "rq3_gaps", None):
        args.rq3_gaps = os.path.abspath(os.path.expanduser(args.rq3_gaps))
    run_decode(args) if args.step == "decode" else run_measure(args)


if __name__ == "__main__":
    main()
