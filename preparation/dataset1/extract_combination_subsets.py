#!/usr/bin/env python3
"""Keeps the conflicts resolved by combination in each partition of the Dataset2 files.

Classifies the resolution of each chunk with `preparation/combination.py` and keeps those
classified as `Combination`.

Inputs: `{name}_{training,validation,testing}.json` in `--data-root`, for each dataset name.
Outputs: `{name}_combination_{training,validation,testing}.json` in the same folder.

    python preparation/dataset1/extract_combination_subsets.py --data-root <data>
"""
import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from combination import strategy  # noqa: E402

NAMES = ['dataset2', 'dataset2_Java', 'dataset2_CSharp', 'dataset2_JavaScript', 'dataset2_TypeScript']


def get_combination_chunks(dataset):
    data = []
    for index, row in dataset.iterrows():
        v1 = row['all_raw_a']
        v2 = row['all_raw_b']
        resolution = row['all_raw_res']
        chunk_id = str(row['merge_id']) + '-' + str(row['chunk_number'])
        data.append([chunk_id, v1, v2, resolution, row['all_raw_base'], strategy(v1, v2, resolution)])
    new_df = pd.DataFrame(data, columns=['chunk_id', 'all_raw_a', 'all_raw_b', 'all_raw_res', 'all_raw_base',
                                         'resolution_strategy'])
    df_combination = new_df[new_df['resolution_strategy'] == 'Combination']
    return df_combination[['chunk_id', 'all_raw_a', 'all_raw_b', 'all_raw_res', 'all_raw_base']]


def save_dataset_to_json(dataset, path):
    with open(path, "w") as json_file:
        json.dump(dataset.to_dict(orient="list"), json_file, indent=4)


def separate_datasets_combination(data_root, name):
    for suffix in ('training', 'testing', 'validation'):
        df = pd.read_json(os.path.join(data_root, f'{name}_{suffix}.json'))
        save_dataset_to_json(get_combination_chunks(df), os.path.join(data_root, f'{name}_combination_{suffix}.json'))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data-root", required=True)
    p.add_argument("--names", default=",".join(NAMES), help="dataset names, comma-separated")
    args = p.parse_args()
    for name in [n for n in args.names.split(",") if n]:
        separate_datasets_combination(os.path.expanduser(args.data_root), name)


if __name__ == "__main__":
    main()
