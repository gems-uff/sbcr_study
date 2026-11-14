#!/usr/bin/env python3
"""Shows, checks or applies a training configuration of MergeGen.

The configuration constants are repeated in three files of the training code. The script
reads them from `configs.py` and writes the three files at once, or checks that they agree
with each other and with a named configuration.

Input: the folder with the MergeGen code (`--dir`).
Output: the table of the constants, and an exit code different from 0 when `--check` fails.

    python mergegen/training/apply_config.py --dir mergegen --check original_test_batch_1
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from configs import CONFIGS, FILES  # noqa: E402

# Each key: (regex that reads it, function that writes the new line).
PATTERNS = {
    "backbone": (
        re.compile(r"^model_type\s*=\s*['\"]([^'\"]+)['\"]", re.M),
        lambda v: f"model_type='{v}'",
    ),
    "max_conflict_length": (
        re.compile(r"^(\s*)'max_conflict_length'\s*:\s*(\d+)", re.M),
        lambda v: f"'max_conflict_length':{v}",
    ),
    "max_resolve_length": (
        re.compile(r"^(\s*)'max_resolve_length'\s*:\s*(\d+)", re.M),
        lambda v: f"'max_resolve_length':{v}",
    ),
    "batch_size": (
        re.compile(r"^(\s*)'batch_size'\s*:\s*(\d+)", re.M),
        lambda v: f"'batch_size':{v}",
    ),
    "test_batch_size": (
        re.compile(r"^(\s*)'test_batch_size'\s*:\s*(\d+)", re.M),
        lambda v: f"'test_batch_size':{v}",
    ),
}
KEYS = ["backbone", "max_conflict_length", "max_resolve_length", "batch_size", "test_batch_size"]


def read(path, key):
    """The value of the key in the file, or None."""
    rx, _ = PATTERNS[key]
    m = rx.search(path.read_text())
    if not m:
        return None
    return m.group(1) if key == "backbone" else int(m.group(2))


def write(path, key, value):
    text = path.read_text()
    rx, build = PATTERNS[key]
    new = build(value)
    if key == "backbone":
        text2, n = rx.subn(new, text, count=1)
    else:
        text2, n = rx.subn(lambda m: m.group(1) + new, text, count=1)
    if n != 1:
        raise SystemExit(f"could not find '{key}' in {path}")
    path.write_text(text2)


def state(d):
    out = {}
    for name, keys in FILES.items():
        p = d / name
        if not p.exists():
            raise SystemExit(f"file not found: {p}")
        out[name] = {k: read(p, k) for k in keys}
    return out


def show(st):
    width = max(len(n) for n in st) + 2
    print(f"{'file':<{width}}" + "".join(f"{k:>22}" for k in KEYS))
    for name, values in st.items():
        line = f"{name:<{width}}"
        for k in KEYS:
            v = values.get(k)
            line += f"{('-' if v is None else str(v)):>22}"
        print(line)


def disagreements(st):
    """Keys whose value differs between the files that declare them."""
    problems = []
    for k in ["backbone", "max_conflict_length", "max_resolve_length"]:
        seen = {n: v[k] for n, v in st.items() if k in v and v[k] is not None}
        if len(set(seen.values())) > 1:
            problems.append(f"{k} differs between the files: {seen}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", required=True, help="folder with the MergeGen training code")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--show", action="store_true", help="show the current configuration")
    g.add_argument("--check", metavar="NAME", help="check against a configuration")
    g.add_argument("--apply", metavar="NAME", help="apply a configuration")
    args = ap.parse_args()

    d = Path(args.dir).expanduser().resolve()
    name = args.check or args.apply
    if name and name not in CONFIGS:
        raise SystemExit(f"unknown configuration: {name}. Available: {', '.join(CONFIGS)}")

    if args.apply:
        cfg = CONFIGS[name]
        for file, keys in FILES.items():
            for k in keys:
                write(d / file, k, cfg[k])
        print(f"configuration '{name}' applied in {d}\n")
        show(state(d))
        return

    st = state(d)
    show(st)
    problems = disagreements(st)
    if problems:
        print("\nthe files DISAGREE:")
        for p in problems:
            print(f"  - {p}")

    if args.check:
        cfg = CONFIGS[name]
        diffs = []
        for file, keys in FILES.items():
            for k in keys:
                current, expected = st[file][k], cfg[k]
                if current != expected:
                    diffs.append(f"  - {file}: {k} = {current}, expected {expected}")
        print()
        if diffs or problems:
            print(f"does NOT match configuration '{name}':")
            print("\n".join(diffs))
            sys.exit(1)
        print(f"matches configuration '{name}'.")
    elif problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
