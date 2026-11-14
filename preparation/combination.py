#!/usr/bin/env python3
"""Classifies how a conflict was resolved, to filter the conflicts resolved by combination.

A library. `strategy` is the `identify_resolution` of
`preparation/dataset1/extract_combination_subsets.py`, with `collections.Counter` in place
of the `multiset` package. `prepare_sbcr.py --check` compares the two on the partitions of
the submitted version.
"""
from collections import Counter


def normalize(line):
    return str(line).replace(" ", "").replace("\t", "").replace("\n", "")


def normalized_lines(text):
    return [normalize(l) for l in str(text).splitlines() if l.strip()]


def strategy(v1, v2, resolution):
    n1, n2, nr = normalize(v1), normalize(v2), normalize(resolution)
    if n1 == nr:
        return "V1"
    if n2 == nr:
        return "V2"
    if nr == n1 + n2:
        return "ConcatV1V2"
    if nr == n2 + n1:
        return "ConcatV2V1"
    resolution_lines = normalized_lines(resolution)
    left = Counter(resolution_lines) - (Counter(normalized_lines(v1)) + Counter(normalized_lines(v2)))
    if sum(left.values()) > 0:
        return "New code"
    if len(resolution_lines) == 0:
        return "None"
    return "Combination"


def is_combination(v1, v2, resolution):
    return strategy(v1, v2, resolution) == "Combination"
