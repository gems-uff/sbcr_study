#!/usr/bin/env python3
"""Rebuilds the reference MergeGen scores against: the resolution cut at `max_resolve_length` tokens.

`run_mergegen.py` compares its candidate with the resolution after tokenizing it, cutting it
at `max_resolve_length` (200) tokens and decoding it back, while SBCR is scored against the
whole resolution. The script rebuilds that cut reference with the same tokenizer and the same
steps (`dataset_parallel.process_data` followed by `see_results`), so the difference between
the two references can be measured. Runs in the `mergegen-train` environment.

Input: `<root>/data/{dataset}.json` and the tokenizer in `<root>/mergeGen/codet5-small-local`.
Output: `<root>/references/{dataset}.json`, chunk_id -> cut reference.

    python preparation/truncated_references.py --root <root>
"""
import argparse
import json
import os
import sys

SPACE = 'Ġ'


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True)
    p.add_argument("--validate", action="store_true",
                   help="compare with the references in the test_OUTPUT files of run_mergegen.py")
    args = p.parse_args()

    root = os.path.expanduser(args.root)
    mergegen = os.path.join(root, "mergeGen")
    os.chdir(mergegen)
    sys.path.insert(0, mergegen)
    from transformers import RobertaTokenizer

    tok = RobertaTokenizer.from_pretrained('./codet5-small-local')
    tok.add_tokens(['<lbra>', '<mbra>', '<rbra>'])
    limit = 200  # max_resolve_length of the original configuration

    def reference(raw):
        ids = tok.convert_tokens_to_ids(tok.tokenize(' '.join(str(raw or "").split())))
        seq = [tok.bos_token_id] + ids + [tok.eos_token_id]
        seq = seq[:limit] if len(seq) > limit else seq + [tok.pad_token_id] * (limit - len(seq))
        seq = seq[1:]  # see_results drops the bos token
        if tok.eos_token_id in seq:
            seq = seq[:seq.index(tok.eos_token_id)]
        return ''.join(tok.convert_ids_to_tokens(seq)).replace(SPACE, " ")

    os.makedirs("../references", exist_ok=True)
    for name in ["dataset1", "dataset2_Java", "dataset2_CSharp", "dataset2_JavaScript", "dataset2_TypeScript"]:
        data = json.load(open(f"../data/{name}.json"))
        out = {str(c): reference(r) for c, r in zip(data["chunk_id"], data["all_raw_res"])}
        json.dump(out, open(f"../references/{name}.json", "w"))
        truncated = sum(1 for c, r in zip(data["chunk_id"], data["all_raw_res"])
                        if len(tok.tokenize(' '.join(str(r or "").split()))) + 2 > limit)
        print(f"{name}: {len(out)} references, {truncated} truncated "
              f"({100*truncated/len(out):.1f}%)", flush=True)

    if args.validate:
        print("\nchecking against the test_OUTPUT files of run_mergegen:")
        import glob
        for folder in sorted(glob.glob("OUTPUT/*/model_*/test_OUTPUT")):
            ds_arm = folder.split("/")[1]
            name = ds_arm.rsplit("_", 1)[0]
            refs = json.load(open(f"../references/{name}.json"))
            data = json.load(open(f"../data/{name}.json"))
            ids = [str(c) for c in data["chunk_id"]]
            equal = total = 0
            for file in glob.glob(f"{folder}/*/*")[:60]:
                text = open(file).read().split("---------------------------------")
                expected = text[0].split("ref_dataloader:\n", 1)[1].rstrip("\n")
                chunk = ids[int(os.path.basename(file))]
                total += 1
                equal += (refs[chunk] == expected)
            if total:
                print(f"  {ds_arm}: {equal}/{total} identical references")


if __name__ == "__main__":
    main()
