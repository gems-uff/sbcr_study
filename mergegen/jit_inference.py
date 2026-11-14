#!/usr/bin/env python3
"""Just-in-time inference: generates MergeGen's candidate for each test conflict and times each step.

The conflict goes in raw and comes out resolved, in one process, and the script times the
tokenization, the structured representation (`git merge-file`), the tensors, the generation
and the decoding. `run_mergegen.py` cannot time the first two, since it reads tensors that a
separate batch job tokenized.

The decoding follows the original MergeGen code, as `run_mergegen.py` does: the encoder runs
apart, `decoder_input_ids` starts with the bos token, three beams, `max_new_tokens` twice the
resolution length, no early stopping, and the text is built from the tokens as `see_results`
builds it. `--validate` checks this against the outputs of `run_mergegen.py`.

Seven runs per arm: the five datasets with their own model, and the two crossed runs of RQ3
between Dataset1 and Dataset2_Java. Runs in the `mergegen-train` or `mergegen-repl` environment.

Inputs, under `--root`: `data/{dataset}.json`, `data/split_{dataset}_{arm}.csv` and
`mergeGen/MODELS/{dataset}_{arm}/best_model.pt`.
Outputs: `mergeGen/JIT/{dataset}_{arm}[__test_{other arm}]/model_{model}_{arm}/candidates.json`
(chunk_id -> candidate) and `times.csv` (seconds per step and chunk).

    python mergegen/jit_inference.py --root <root> --arm mg
"""
import argparse
import json
import os
import sys
import time

import pandas as pd

# (dataset, model); None is the model of the dataset itself. The last two are the crossed runs of RQ3.
PAIRS = [
    ("dataset1", None),
    ("dataset2_TypeScript", None),
    ("dataset2_CSharp", None),
    ("dataset2_JavaScript", None),
    ("dataset2_Java", None),
    ("dataset1", "dataset2_Java"),
    ("dataset2_Java", "dataset1"),
]

SPACE = 'Ġ'  # the space marker of the CodeT5 tokenizer


def build_text(ids, tokenizer):
    """As see_results: cut at the eos token and join the tokens."""
    ids = list(ids)
    if tokenizer.eos_token_id in ids:
        ids = ids[:ids.index(tokenizer.eos_token_id)]
    return ''.join(tokenizer.convert_ids_to_tokens(ids)).replace(SPACE, " ")


def generate(tool, base, v1, v2, synchronize):
    """The whole sequence, with a timer between the steps."""
    import torch
    from transformers.modeling_outputs import BaseModelOutputWithPastAndCrossAttentions

    t0 = time.perf_counter()
    tokens_base = tool.tokenizer.tokenize(' '.join(str(base or "").split()))
    tokens_a = tool.tokenizer.tokenize(' '.join(str(v1 or "").split()))
    tokens_b = tool.tokenizer.tokenize(' '.join(str(v2 or "").split()))
    t1 = time.perf_counter()

    conflict_tokens = tool._git_merge_single(tokens_base, tokens_a, tokens_b)
    t2 = time.perf_counter()

    ids = tool.tokenizer.convert_tokens_to_ids(conflict_tokens)
    ids = tool._pad_sequence(ids, tool.max_conflict_length, tool.tokenizer.pad_token_id)
    model_input = torch.tensor([ids], device=tool.device)
    mask = model_input != tool.tokenizer.pad_token_id
    synchronize()
    t3 = time.perf_counter()

    with torch.no_grad():
        state = tool.model.encoder(input_ids=model_input, attention_mask=mask,
                                   return_dict=True)['last_hidden_state']
        output = tool.model.generate(
            encoder_outputs=BaseModelOutputWithPastAndCrossAttentions(last_hidden_state=state),
            attention_mask=mask,
            decoder_input_ids=(torch.ones(1, 1) * tool.tokenizer.bos_token_id).long().to(tool.device),
            num_beams=tool.num_beams,
            num_return_sequences=tool.num_beams,
            max_new_tokens=tool.max_resolve_length * 2,
        )
    synchronize()
    t4 = time.perf_counter()

    output = output[:, 1:].view(1, tool.num_beams, -1)
    candidate = build_text(output[0][0].tolist(), tool.tokenizer)
    t5 = time.perf_counter()

    return candidate, {
        "tokenization": t1 - t0,
        "git_merge": t2 - t1,
        "tensors": t3 - t2,
        "generation": t4 - t3,
        "decoding": t5 - t4,
        "end_to_end": t5 - t0,
    }


def load_conflicts(name, arm):
    data = json.load(open(f"../data/{name}.json"))
    assignment = pd.read_csv(f"../data/split_{name}_{arm}.csv", dtype={"chunk_id": str})
    test = set(assignment[assignment.partition == "test"].chunk_id)
    ids = list(map(str, data["chunk_id"]))
    indices = [i for i, c in enumerate(ids) if c in test]
    return data, ids, indices


def validate(tool, name, model, arm, synchronize, how_many):
    """Checks that the candidate equals what run_mergegen.py produced."""
    expected_path = f"OUTPUT/{name}_{arm}/model_{model}_{arm}/total_gen_output_test_beam.json"
    index_path = f"AUX_FILES/{name}_{arm}/all_index_{name}_{arm}"
    if not (os.path.exists(expected_path) and os.path.exists(index_path)):
        return None
    expected = json.load(open(expected_path))
    order = json.load(open(index_path))["test"]
    data, _, _ = load_conflicts(name, arm)

    equal = 0
    for j in range(min(how_many, len(order))):
        i = order[j]
        candidate, _ = generate(tool, data["all_raw_base"][i], data["all_raw_a"][i], data["all_raw_b"][i], synchronize)
        target = expected[j][0] if isinstance(expected[j], list) else expected[j]
        equal += (candidate == target)
    return equal, min(how_many, len(order))


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--root", required=True, help="experiment root")
    p.add_argument("--arm", required=True, help="arm of the model")
    p.add_argument("--test-of", default=None,
                   help="use the test partition of this arm instead of the model's own, so that "
                        "models of different arms are evaluated on the same conflicts")
    p.add_argument("--validate", action="store_true", help="only check the equivalence with run_mergegen.py")
    p.add_argument("--validation-sample", type=int, default=50)
    args = p.parse_args()

    mergegen = os.path.join(os.path.expanduser(args.root), "mergeGen")
    os.chdir(mergegen)
    sys.path.insert(0, mergegen)
    import torch
    from mergegen_inference import MergeInference

    synchronize = torch.cuda.synchronize if torch.cuda.is_available() else (lambda: None)

    for name, model in PAIRS:
        model = model or name
        model_path = f"MODELS/{model}_{args.arm}/best_model.pt"
        if not os.path.exists(model_path):
            print(f"{name} <- {model}: model missing, skipping", flush=True)
            continue

        suffix = f"__test_{args.test_of}" if args.test_of else ""
        destination = f"JIT/{name}_{args.arm}{suffix}/model_{model}_{args.arm}"
        if not args.validate and os.path.exists(f"{destination}/times.csv"):
            print(f"{name} <- {model}: already done, skipping", flush=True)
            continue

        tool = MergeInference(model_path=model_path)

        if args.validate and not args.test_of:
            r = validate(tool, name, model, args.arm, synchronize, args.validation_sample)
            if r is None:
                print(f"{name} <- {model}: no output of run_mergegen to compare with", flush=True)
            else:
                equal, total = r
                print(f"{name} <- {model}: {equal}/{total} identical candidates", flush=True)
        else:
            data, ids, indices = load_conflicts(name, args.test_of or args.arm)
            os.makedirs(destination, exist_ok=True)
            candidates, times = {}, []
            start = time.time()
            for k, i in enumerate(indices):
                candidate, t = generate(tool, data["all_raw_base"][i], data["all_raw_a"][i],
                                        data["all_raw_b"][i], synchronize)
                candidates[ids[i]] = candidate
                t["chunk_id"] = ids[i]
                times.append(t)
                if (k + 1) % 500 == 0:
                    print(f"  {name} <- {model}: {k+1}/{len(indices)} "
                          f"({(time.time()-start)/(k+1):.3f} s/conflict)", flush=True)
            json.dump(candidates, open(f"{destination}/candidates.json", "w"))
            pd.DataFrame(times).to_csv(f"{destination}/times.csv", index=False)
            print(f"{name} <- {model}: {len(indices)} conflicts, "
                  f"{(time.time()-start)/60:.1f} min", flush=True)

        del tool
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
