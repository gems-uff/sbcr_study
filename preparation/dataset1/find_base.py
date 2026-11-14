#!/usr/bin/env python3
"""Rebuilds the base version of each Dataset1 chunk from the whole base file and the context lines.

For each chunk, it looks for the lines of `before_context` and `after_context` in the base
file, growing the fragments from the conflict outwards until exactly one pair of positions
matches, and takes the text between them as the base of the chunk. It writes empty content
when a version has 20,000 characters or more (the limit of SBCR) and when the region cannot
be located at a single position.

Input: a JSON file with the columns `chunk_id`, `all_raw_base` (the whole base file),
`all_raw_a`, `all_raw_b`, `before_context` and `after_context`.
Output: JSON lines with `chunk_id`, `line_start`, `line_end` and `content`.

    python preparation/dataset1/find_base.py --input <dataset1_with_context.json> --output <base_extraction.json>
"""
import argparse

import pandas as pd


def locate_conflict_region(base_content, upper_context, lower_context):
    upper_lines = upper_context.splitlines(keepends=True)
    lower_lines = lower_context.splitlines(keepends=True)

    for i in range(1, len(upper_lines)):
        upper_fragment = ''.join(upper_lines[-i:])
        upper_positions = find_occurrences(base_content, upper_fragment)
        if len(upper_positions) > 0:
            for j in range(1, len(lower_lines) + 1):

                lower_fragment = ''.join(lower_lines[:j])
                lower_positions = find_occurrences(base_content, lower_fragment)
                count_possible_matches = 0
                last_pos_upper = None
                last_pos_lower = None
                for pos_upper in upper_positions:
                    for pos_lower in lower_positions:
                        if pos_lower > pos_upper:
                            count_possible_matches += 1
                            last_pos_upper = pos_upper
                            last_pos_lower = pos_lower

                if count_possible_matches == 1:
                    line_start = base_content[:last_pos_upper + len(upper_fragment)].count('\n')
                    line_end = base_content[:last_pos_lower].count('\n')
                    conflict_content = base_content[last_pos_upper + len(upper_fragment):last_pos_lower]
                    return [line_start, line_end, conflict_content]
    return []


def find_occurrences(content, fragment):
    positions = []
    pos = content.find(fragment)
    while pos != -1:
        positions.append(pos)
        pos = content.find(fragment, pos + 1)
    return positions


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    data = []
    count = 1
    df = pd.read_json(args.input)
    for index, row in df.iterrows():
        print(f' ({count}/{len(df)})Analyzing chunk: ', row['chunk_id'])
        if len(row['all_raw_a']) < 20000 and len(row['all_raw_b']) < 20000:
            conflict_region = locate_conflict_region(row['all_raw_base'], row['before_context'], row['after_context'])
            if len(conflict_region) > 0:
                line_start = conflict_region[0]
                line_end = conflict_region[1]
                content = ''.join(conflict_region[2])
                data.append([row['chunk_id'], int(line_start), int(line_end), content])
            else:
                data.append([row['chunk_id'], '', '', ''])
        else:
            data.append([row['chunk_id'], '', '', ''])

        if count % 50 == 0:
            pd.DataFrame(data, columns=['chunk_id', 'line_start', 'line_end', 'content']).to_json(
                args.output, orient='records', lines=True)
        count += 1

    pd.DataFrame(data, columns=['chunk_id', 'line_start', 'line_end', 'content']).to_json(
        args.output, orient='records', lines=True)


if __name__ == "__main__":
    main()
