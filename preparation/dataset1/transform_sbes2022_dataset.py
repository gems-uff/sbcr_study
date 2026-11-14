#!/usr/bin/env python3
"""Turns the SBES 2022 dataset into Dataset1, in the format MergeGen and SBCR read.

`get_clean_solution` cuts from the resolution the context lines around the chunk (three
before and three after are assumed), and returns `None` when the context of the resolution
does not match that of the chunk. Those chunks are dropped.

Input: the SBES 2022 dataset with the columns `base`, `v1`, `v2`, `solution`, `before_context`,
`after_context` and `chunk_id` (`dataset_processed_base.json` of its FigShare item).
Output: `dataset1_complete.json`, with `all_raw_base`, `all_raw_a`, `all_raw_b`, `all_raw_res` and `chunk_id`.

    python preparation/dataset1/transform_sbes2022_dataset.py --input <sbes2022_data.json> --output <data>/dataset1_complete.json
"""
import argparse
import json

import pandas as pd


def get_clean_solution(solution, before_context, after_context):
    solution = normalize_lines(solution.splitlines()).copy()
    before_context = normalize_lines(before_context.splitlines())
    after_context = normalize_lines(after_context.splitlines())

    if len(solution) >= 6:
        # the last of the first three lines of the solution that is in before_context
        solution_before_context_candidate = solution[:3]
        last_line_before_context = 0
        for index, line in enumerate(solution_before_context_candidate):
            if line in before_context:
                last_line_before_context = index

        # the first of the last three lines of the solution that is in after_context
        solution_after_context_candidate = solution[-3:]
        first_line_after_context = len(solution)
        for index, line in enumerate(solution_after_context_candidate):
            if line in after_context:
                first_line_after_context = len(solution) - (3 - index)
                break
        solution_before_context = solution[:last_line_before_context + 1]
        solution_after_context = solution[first_line_after_context:]
        if (equivalent_context(solution_before_context, before_context)
                and equivalent_context(solution_after_context, after_context)):
            return solution[last_line_before_context + 1:first_line_after_context]
        else:
            return None
    return solution


def normalize_line(line):
    return line


def normalize_lines(lines):
    normalized_lines = []
    for line in lines:
        normalized_lines.append(normalize_line(line))
    return normalized_lines


def equivalent_context(context_solution, context_chunk):
    context_solution = remove_empty_lines(context_solution)
    context_chunk = remove_empty_lines(context_chunk)
    if len(context_solution) != len(context_chunk):
        return False
    for i in range(len(context_solution)):
        if context_solution[i] != context_chunk[i]:
            return False
    return True


def remove_empty_lines(lines):
    cleaned_lines = []
    for line in lines:
        if line != '':
            cleaned_lines.append(line)
    return cleaned_lines


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    columns = ['all_raw_base', 'all_raw_a', 'all_raw_b', 'all_raw_res', 'chunk_id']
    new_data = []
    data = pd.read_json(args.input)
    for index, row in data.iterrows():
        new_solution = get_clean_solution(row['solution'], row['before_context'], row['after_context'])
        if new_solution is not None:
            new_data.append([row['base'], row['v1'], row['v2'], '\n'.join(new_solution), row['chunk_id']])

    json_data = pd.DataFrame(new_data, columns=columns).to_dict(orient="list")
    with open(args.output, "w") as json_file:
        json.dump(json_data, json_file, indent=4)


if __name__ == "__main__":
    main()
