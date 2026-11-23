#!/usr/bin/env python3
"""Checks the published prompts against the run records of the RQ4 archive.

The run records hold the SHA-256 of the prompt each call sent (`prompt_sha256`), and those of the
derivation also that of the schema (`schema_sha256`). The script renders the prompts from the
published files with the code of `run_annotator.py` and compares the hashes:

- the labeling prompt of a version of the annotator's instructions, rendered with the coding
  scheme, against every labeling record of a folder of runs;
- the derivation prompt and its schema against every derivation record of a folder.

The description records hold no hash of their prompt, so part 1 of the instructions is not
checked here.

Inputs: the instructions (`--instructions`), the scheme (`--scheme`), the folders of labeling
records (`--labeling`), the derivation prompt (`--derivation-prompt`) and the folder of its records
(`--derivation`). Output: one line per folder and a summary; exit code 1 if a hash differs.

    python validation/check_prompts.py --instructions docs/annotator-instructions-v1.md \
        --scheme analysis/rq4/scheme/coding-scheme.json \
        --labeling <archives>/rq4/annotator/block1-labeling <archives>/rq4/annotator/scale-labeling \
        --derivation-prompt docs/derivation-prompt.md --derivation <archives>/rq4/derivation/block1/runs
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

PACKAGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PACKAGE, "analysis", "rq4", "annotator"))
sys.path.insert(0, os.path.join(PACKAGE, "analysis", "rq4"))

from run_annotator import BEGIN, END, labeling_prompt, part2, sha256  # noqa: E402


def records(folder, step):
    for path in sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True)):
        if path.endswith(".response.json"):
            continue
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        if isinstance(rec, dict) and rec.get("step") == step:
            yield path, rec


def derivation_prompt_and_schema(text):
    """The prompt and the schema of the derivation, read as the derivation run read them."""
    m = re.search(rf"^{re.escape(BEGIN)}$(.*?)^{re.escape(END)}$", text, re.S | re.M)
    prompt = m.group(1).strip() + "\n"
    rest = text[text.index("## JSON schema of the output"):]
    schema = json.loads(re.search(r"```json\n(.*?)```", rest, re.S).group(1))
    return prompt, schema


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--instructions", help="annotator's instructions (docs/annotator-instructions-v<n>.md)")
    p.add_argument("--scheme", help="coding scheme (analysis/rq4/scheme/coding-scheme.json)")
    p.add_argument("--labeling", nargs="*", default=[], help="folders of labeling records")
    p.add_argument("--derivation-prompt", help="docs/derivation-prompt.md")
    p.add_argument("--derivation", help="folder of the derivation records")
    args = p.parse_args()

    failed = False
    if args.labeling:
        with open(args.instructions, encoding="utf-8") as fh:
            instructions = fh.read()
        with open(args.scheme, encoding="utf-8") as fh:
            scheme = json.load(fh)
        expected = sha256(labeling_prompt(part2(instructions), scheme))
        print(f"labeling prompt of {os.path.basename(args.instructions)} with the scheme: {expected}")
        for folder in args.labeling:
            hashes = [rec.get("prompt_sha256") for _, rec in records(folder, "labeling")]
            equal = sum(h == expected for h in hashes)
            print(f"  {os.path.basename(os.path.normpath(folder))}: {equal}/{len(hashes)} records with this prompt")
            failed |= equal != len(hashes) or not hashes

    if args.derivation:
        with open(args.derivation_prompt, encoding="utf-8") as fh:
            prompt, schema = derivation_prompt_and_schema(fh.read())
        want_prompt = sha256(prompt)
        want_schema = sha256(json.dumps(schema, sort_keys=True))
        print(f"derivation prompt: {want_prompt}, schema: {want_schema}")
        found = list(records(args.derivation, "derivation"))
        equal = sum(r.get("prompt_sha256") == want_prompt and r.get("schema_sha256") == want_schema
                    for _, r in found)
        print(f"  {equal}/{len(found)} derivation records with this prompt and schema")
        failed |= equal != len(found) or not found

    print("\nprompts " + ("DIFFER" if failed else "equal to the run records"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
