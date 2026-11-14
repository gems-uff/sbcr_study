#!/usr/bin/env python3
"""Per-conflict table of the model of the characteristics that predict the winner, and the checks before the fit.

Do the characteristics the submitted version of the study used to route conflicts between the
tools (size imbalance between the versions, exposure to MergeGen's token limit, non-English
content) predict whether SBCR or MergeGen gets closer to the resolution? This script builds the
data `fit_models.R` reads, on the combination subset of the test partition of partition 1. It
fits no model. One row per conflict, in `conflicts.csv`:

- response: `sbcr`, `mergegen` and `difference` (SBCR − MergeGen), with all whitespace removed
  and SBCR scored 0 above its size limit; `sbcr_wins` is 1 or 0, and empty on a tie;
- `imbalance`: |V1 − V2| / (V1 + V2), sizes in characters with all whitespace removed, 0 when both
  versions are empty;
- `input_above_500`: from `population_tokens.csv` (the input exceeds MergeGen's 500-token limit);
- `outside_ascii_letters`, `outside_ascii_share`, `outside_ascii_any`: letters outside ASCII
  (Unicode category `L*`, code point above 127) in the base, V1 and V2, their share over the
  characters with all whitespace removed, and whether there is any;
- controls: `log_size` = log(1 + n), n the characters of the base, V1 and V2 with all whitespace
  removed; `language`; `source` (Dataset1 or Dataset2); `dataset`;
- groups: `project` and `merge` (project @ merge commit), from the metadata of the datasets;
- `empty_versions` and `empty_input`, the zero denominators;
- `old_rq4_extreme`: one of the 100 extreme cases of the RQ4 of the submitted version.

Checks: `detector_check.csv` and `detector_check_summary.csv` (the non-English detector on the 10
conflicts per dataset in which SBCR did best in the submitted RQ4, against the counts of its
table), `prevalence.csv`, `zero_denominators.csv`, `collinearity.csv` (variance inflation
factors), `imbalance_quantiles.csv` and `old_extremes_in_test.csv`. `build_table.json` holds the
parameters, the counts and the SHA-256 of the inputs.

With `--decoded`, MergeGen's similarity of the candidates whose text changes once decoded to
UTF-8 comes from `changed_candidates.csv` of `analysis/datasets/decoding_effect.py`.

Inputs: the root of partition 1 (`--root`), the datasets with their metadata (`--metadata`) and a
checkout of this repository at the tag of the submitted version, for its RQ4 lists (`--package`).
Outputs: the CSVs above, in `--out`.

    python analysis/winner/build_table.py --root <root> --out <dir> --metadata <data> \
        --package <checkout of the submitted version> [--decoded <changed_candidates.csv>]
"""

import argparse
import hashlib
import json
import math
import os
import sys
import unicodedata

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
for folder in (os.path.join(HERE, "..", "rq1_rq3"), os.path.join(HERE, "..", "similarity"),
               os.path.join(HERE, "..", "datasets"), os.path.join(HERE, "..", "..", "preparation")):
    sys.path.insert(0, folder)
from compare_approaches import evaluated_sets, load_mergegen, paired_frames, split_key  # noqa: E402
from survey import normalize_project  # noqa: E402
from sbcr_scores import load_sbcr_similarities  # noqa: E402
from sbcr_similarity import normalize  # noqa: E402
ARM = "mg"
DATASETS = ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]
LANGUAGE = {"dataset1": "Java", "dataset2_Java": "Java", "dataset2_CSharp": "CSharp",
            "dataset2_JavaScript": "JavaScript", "dataset2_TypeScript": "TypeScript"}
# "Non-English content" among the 10 conflicts per dataset in which SBCR did best, in the table
# of the RQ4 of the submitted version of the paper.
PAPER_NON_ENGLISH = {"dataset1": 1, "dataset2_Java": 1, "dataset2_CSharp": 0,
                     "dataset2_JavaScript": 4, "dataset2_TypeScript": 1}
OLD_EXTREMES = 10
ZERO_THRESHOLD = 0.01
LISTS = os.path.join("analysis", "intermediary_data", "rq4_{dataset}_qualitative_list_{side}.csv")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def outside_ascii_letters(text):
    return sum(1 for c in text if ord(c) > 127 and unicodedata.category(c).startswith("L"))


def features(base, v1, v2):
    """Input characteristics of a conflict, over its text with all whitespace removed."""
    base, v1, v2 = normalize(base or ""), normalize(v1 or ""), normalize(v2 or "")
    n = len(base) + len(v1) + len(v2)
    letters = outside_ascii_letters(base + v1 + v2)
    versions = len(v1) + len(v2)
    return {"size_chars": n, "log_size": math.log1p(n), "v1_chars": len(v1), "v2_chars": len(v2),
            "imbalance": abs(len(v1) - len(v2)) / versions if versions else 0.0,
            "outside_ascii_letters": letters, "outside_ascii_share": letters / n if n else 0.0,
            "outside_ascii_any": letters > 0, "empty_versions": versions == 0, "empty_input": n == 0}


def chunk_ids(data):
    """Chunk ids as the split writes them: `merge_id-chunk_number` in Dataset2."""
    if "chunk_id" in data:
        return [str(c) for c in data["chunk_id"]]
    return [f"{m}-{c}" for m, c in zip(data["merge_id"], data["chunk_number"])]


def load_metadata(folder, dataset):
    """Project and merge of every chunk, as `survey.py` reads them."""
    if dataset == "dataset1":
        path = os.path.join(folder, "dataset1_metadata.csv")
        m = pd.read_csv(path).rename(columns={"project": "project", "sha": "commit"})
    else:
        path = os.path.join(folder, f"{dataset}_metadata.json")
        m = pd.DataFrame(json.load(open(path))).rename(columns={"repo": "project", "commitHash": "commit"})
    m["chunk_id"] = m.chunk_id.astype(str)
    if m.chunk_id.duplicated().any():
        raise RuntimeError(f"{path} has repeated chunk ids")
    m["project"] = m.project.map(normalize_project)
    m["merge"] = m.project + "@" + m["commit"].astype(str)
    return m[["chunk_id", "project", "merge"]], path


def response(root, decoded=None):
    """SBCR and MergeGen per conflict of the test partition of the `mg` arm.

    With `decoded`, the changed candidates take their decoded similarity. Returns also how many
    conflicts of the table that changes.
    """
    evaluated = evaluated_sets(root)
    sb = load_sbcr_similarities(root)
    sb = sb[sb.partition == sb.arm]
    mg = load_mergegen(root, evaluated)
    changed = 0
    if decoded:
        from decoding_effect import corrected_mergegen
        mg = mg[mg.arm == ARM]
        stored = mg.mergegen.to_numpy()
        mg = corrected_mergegen(mg, pd.read_csv(decoded, dtype={"chunk_id": str}))
        own = (mg.dataset == mg.model).to_numpy()
        changed = int(((mg.mergegen.to_numpy() != stored) & own).sum())
    j, _ = paired_frames(sb, mg)
    j = j[j.arm == ARM]
    seeds = sorted(sb[sb.arm == ARM].seed.unique())
    return j[["dataset", "chunk_id", "sbcr", "mergegen", "out_of_limits"]], evaluated, seeds, changed


def test_conflicts(root, dataset):
    path = os.path.join(root, "data", f"{split_key(dataset, ARM)}_testing.json")
    data = json.load(open(path))
    rows = [{"chunk_id": c, **features(b, v1, v2)}
            for c, b, v1, v2 in zip(chunk_ids(data), data["all_raw_base"], data["all_raw_a"], data["all_raw_b"])]
    return pd.DataFrame(rows), path


def old_extremes(package, metadata, dataset):
    """The 10 conflicts per side of the submitted RQ4, with the detector applied to each."""
    data = json.load(open(os.path.join(metadata, f"{dataset}_complete.json")))
    content = {c: (b, v1, v2) for c, b, v1, v2 in
               zip(chunk_ids(data), data["all_raw_base"], data["all_raw_a"], data["all_raw_b"])}
    rows, paths = [], []
    for side, ascending in [("SBCRBetter", False), ("MergegenBetter", True)]:
        path = os.path.join(package, LISTS.format(dataset=dataset, side=side))
        paths.append(path)
        lst = pd.read_csv(path, dtype={"chunk_id": str})
        expected = lst["diff"].sort_values(ascending=ascending, kind="stable").to_numpy()
        if not np.array_equal(lst["diff"].to_numpy(), expected):
            raise RuntimeError(f"{path} is not sorted by `diff`, so its first rows are not the extremes")
        if lst["diff"].iloc[OLD_EXTREMES - 1] == lst["diff"].iloc[OLD_EXTREMES]:
            raise RuntimeError(f"{path}: rows {OLD_EXTREMES} and {OLD_EXTREMES + 1} tie, the cut is ambiguous")
        for rank, r in enumerate(lst.head(OLD_EXTREMES).itertuples(), start=1):
            if r.chunk_id not in content:
                raise RuntimeError(f"{dataset}: chunk {r.chunk_id} of {path} is not in the dataset file")
            f = features(*content[r.chunk_id])
            rows.append({"dataset": dataset, "side": side, "rank": rank, "chunk_id": r.chunk_id,
                         "old_difference": r.diff, "outside_ascii_letters": f["outside_ascii_letters"],
                         "outside_ascii_share": f["outside_ascii_share"], "marked": f["outside_ascii_any"]})
    return pd.DataFrame(rows), paths


def vif(x, i):
    """1 / (1 − R²) of column i regressed by least squares on the others, which hold a constant."""
    y, others = x[:, i], np.delete(x, i, axis=1)
    residual = y - others @ np.linalg.lstsq(others, y, rcond=None)[0]
    r2 = 1 - (residual @ residual) / ((y - y.mean()) @ (y - y.mean()))
    return 1 / (1 - r2)


def vif_table(t, non_english):
    """Variance inflation factor of each fixed effect, with dataset as dummies (Dataset1 the reference)."""
    x = t[["imbalance", "input_above_500", "log_size", non_english]].astype(float)
    x = pd.concat([x, pd.get_dummies(t.dataset, drop_first=True, dtype=float)], axis=1)
    x.insert(0, "const", 1.0)
    return pd.DataFrame([{"non_english_as": non_english, "term": c, "vif": vif(x.to_numpy(), i)}
                         for i, c in enumerate(x.columns) if c != "const"])


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--metadata", required=True, help="folder with the datasets and their metadata")
    p.add_argument("--package", required=True, help="checkout of this repository at the tag of the submitted version")
    p.add_argument("--decoded", help="changed_candidates.csv of decoding_effect.py")
    args = p.parse_args()
    root, out = os.path.expanduser(args.root), os.path.expanduser(args.out)
    metadata, package = os.path.expanduser(args.metadata), os.path.expanduser(args.package)
    decoded = os.path.expanduser(args.decoded) if args.decoded else None
    os.makedirs(out, exist_ok=True)
    inputs = [decoded] if decoded else []

    resp, evaluated, seeds, decoded_changed = response(root, decoded)
    tokens_path = os.path.join(root, "population_tokens.csv")
    tokens = pd.read_csv(tokens_path, dtype={"chunk_id": str})
    tokens = tokens[tokens.arm == ARM][["dataset", "chunk_id", "input_above_500"]]
    inputs.append(tokens_path)

    parts, extremes = [], []
    for dataset in DATASETS:
        conflicts, path = test_conflicts(root, dataset)
        inputs.append(path)
        meta, meta_path = load_metadata(metadata, dataset)
        inputs.append(meta_path)
        conflicts = conflicts.merge(meta, on="chunk_id", how="left", validate="one_to_one")
        conflicts.insert(0, "dataset", dataset)
        parts.append(conflicts)
        e, paths = old_extremes(package, metadata, dataset)
        inputs += paths + [os.path.join(metadata, f"{dataset}_complete.json")]
        e["in_test"] = e.chunk_id.isin(evaluated[split_key(dataset, ARM)])
        extremes.append(e)
    t = pd.concat(parts, ignore_index=True)
    extremes = pd.concat(extremes, ignore_index=True)

    n_test = len(t)
    t = t.merge(resp, on=["dataset", "chunk_id"], how="left", validate="one_to_one")
    t = t.merge(tokens, on=["dataset", "chunk_id"], how="left", validate="one_to_one")
    missing = {c: int(t[c].isna().sum()) for c in ["project", "merge", "sbcr", "mergegen", "input_above_500"]}
    if any(missing.values()):
        raise RuntimeError(f"conflicts with a missing value, which lme4 would drop without warning: {missing}")
    t["difference"] = t.sbcr - t.mergegen
    t["sbcr_wins"] = np.where(t.sbcr > t.mergegen, 1.0, np.where(t.sbcr < t.mergegen, 0.0, np.nan))
    t["language"] = t.dataset.map(LANGUAGE)
    t["source"] = np.where(t.dataset == "dataset1", "Dataset1", "Dataset2")
    t["input_above_500"] = t.input_above_500.astype(bool)
    old_ids = set(zip(extremes.dataset, extremes.chunk_id))
    t["old_rq4_extreme"] = [(d, c) in old_ids for d, c in zip(t.dataset, t.chunk_id)]
    columns = ["dataset", "language", "source", "chunk_id", "project", "merge",
               "sbcr", "mergegen", "difference", "sbcr_wins", "out_of_limits",
               "imbalance", "input_above_500", "outside_ascii_letters", "outside_ascii_share", "outside_ascii_any",
               "size_chars", "log_size", "v1_chars", "v2_chars", "empty_versions", "empty_input", "old_rq4_extreme"]
    t = t[columns]
    t.to_csv(os.path.join(out, "conflicts.csv"), index=False)

    # detector against the submitted RQ4
    extremes.to_csv(os.path.join(out, "detector_check.csv"), index=False)
    marked = extremes.groupby(["dataset", "side"]).marked.sum().unstack("side")
    check = pd.DataFrame({"dataset": DATASETS,
                          "paper_non_english": [PAPER_NON_ENGLISH[d] for d in DATASETS],
                          "marked_sbcr_better": [int(marked.loc[d, "SBCRBetter"]) for d in DATASETS],
                          "marked_mergegen_better": [int(marked.loc[d, "MergegenBetter"]) for d in DATASETS]})
    check["passes"] = check.marked_sbcr_better >= check.paper_non_english
    check.to_csv(os.path.join(out, "detector_check_summary.csv"), index=False)

    # prevalence of letters outside ASCII
    def prevalence(g, name):
        m = g[g.outside_ascii_any].outside_ascii_share
        return {"dataset": name, "n": len(g), "marked": int(g.outside_ascii_any.sum()),
                "marked_share": g.outside_ascii_any.mean(),
                "share_median_marked": m.median() if len(m) else np.nan,
                "share_p90_marked": m.quantile(0.9) if len(m) else np.nan,
                "share_max": m.max() if len(m) else np.nan}
    prev = pd.DataFrame([prevalence(g, d) for d, g in t.groupby("dataset", sort=False)] + [prevalence(t, "all")])
    prev.to_csv(os.path.join(out, "prevalence.csv"), index=False)

    # zero denominators
    zero = t.groupby("dataset", sort=False).agg(n=("chunk_id", "size"), empty_versions=("empty_versions", "sum"),
                                               empty_input=("empty_input", "sum")).reset_index()
    zero["empty_versions_share"] = zero.empty_versions / zero.n
    zero["empty_input_share"] = zero.empty_input / zero.n
    fourth_sensitivity = bool((zero[["empty_versions_share", "empty_input_share"]] > ZERO_THRESHOLD).any().any())
    zero.to_csv(os.path.join(out, "zero_denominators.csv"), index=False)

    # collinearity
    corr = float(np.corrcoef(t.input_above_500.astype(float), t.log_size)[0, 1])
    vif = pd.concat([vif_table(t, "outside_ascii_share"), vif_table(t, "outside_ascii_any")], ignore_index=True)
    vif = pd.concat([vif, pd.DataFrame([{"non_english_as": "", "term": "corr(input_above_500, log_size)",
                                         "vif": corr}])], ignore_index=True)
    vif.to_csv(os.path.join(out, "collinearity.csv"), index=False)

    # imbalance, for the threshold of balanced versions
    q = [0.1, 0.25, 0.5, 0.75, 0.9]
    imb = t.groupby("dataset", sort=False).imbalance.quantile(q).unstack()
    imb.loc["all"] = t.imbalance.quantile(q)
    imb.columns = [f"q{int(c * 100)}" for c in imb.columns]
    imb.reset_index().to_csv(os.path.join(out, "imbalance_quantiles.csv"), index=False)

    # extreme cases of the submitted RQ4 in this test set
    in_test = extremes.groupby(["dataset", "side"], sort=False).in_test.sum().unstack("side").reset_index()
    in_test.to_csv(os.path.join(out, "old_extremes_in_test.csv"), index=False)

    summary = {
        "root": root, "arm": ARM, "sbcr_seeds": seeds, "conflicts": n_test,
        "decoded": decoded, "decoded_changed": decoded_changed,
        "per_dataset": t.groupby("dataset", sort=False).size().to_dict(),
        "projects": int(t.project.nunique()), "merges": int(t["merge"].nunique()),
        "ties": int(t.sbcr_wins.isna().sum()), "out_of_limits": int(t.out_of_limits.sum()),
        "input_above_500": int(t.input_above_500.sum()),
        "detector_passes_all": bool(check.passes.all()),
        "fourth_sensitivity_needed": fourth_sensitivity,
        "corr_input_above_500_log_size": corr,
        "old_extremes_in_test": int(extremes.in_test.sum()),
        "inputs": {os.path.relpath(f, os.path.expanduser("~")): sha256(f) for f in sorted(set(inputs))},
    }
    json.dump(summary, open(os.path.join(out, "build_table.json"), "w"), indent=2)

    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(f"conflicts: {n_test}  {summary['per_dataset']}")
        if decoded:
            print(f"MergeGen candidates decoded: {decoded_changed} conflicts change")
        print(f"projects: {summary['projects']}  merges: {summary['merges']}  ties: {summary['ties']}  "
              f"out of SBCR's limits: {summary['out_of_limits']}  input above 500 tokens: {summary['input_above_500']}")
        print("\n--- detector against the submitted RQ4 ---")
        print(check.to_string(index=False))
        print("\n--- letters outside ASCII ---")
        print(prev.round(4).to_string(index=False))
        print("\n--- zero denominators ---")
        print(zero.round(4).to_string(index=False))
        print(f"fourth sensitivity analysis needed: {fourth_sensitivity}")
        print(f"\ncorrelation input_above_500 x log_size: {corr:.3f}")
        print(vif.round(3).to_string(index=False))
        print("\n--- imbalance quantiles ---")
        print(imb.round(3).to_string())
        print("\n--- extreme cases of the submitted RQ4 in this test set ---")
        print(in_test.to_string(index=False))
    print(f"\nwritten in {out}")


if __name__ == "__main__":
    main()
