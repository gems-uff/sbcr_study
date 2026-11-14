#!/usr/bin/env python3
"""Smoke test of the MergeGen environment.

Stops at the first step that fails:

1. checks the versions of the pinned dependencies, the GPU and `git`;
2. loads the checkpoint over its backbone;
3. runs the model over the ten conflicts of `fixtures/smoke_conflicts.json` and compares the
   SHA-256 of the outputs with the reference of `reference_digests.json`, which catches a
   dependency change that alters the output of the model without breaking anything visibly.

Inputs: the backbone folder (`--backbone`, `codet5-small-local`), a trained checkpoint
(`--checkpoint`, for example `dataset2_Java_mg/best_model.pt` of the models archive) and the
name of its reference digest (`--reference`).
Output: the report, on the standard output; exit code 1 on failure.

    python mergegen/environment/verify_env.py --backbone <dir>/codet5-small-local \
        --checkpoint <models>/dataset2_Java_mg/best_model.pt --reference dataset2_Java_mg
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

EXPECTED = {
    "python": "3.9.23",
    "torch": "2.8.0+cu129",
    "transformers": "4.19.2",
    "tokenizers": "0.12.1",
    "numpy": "2.0.2",
    "pandas": "2.3.1",
    "huggingface_hub": "0.33.4",
}


def fail(msg):
    print(f"FAILED: {msg}")
    sys.exit(1)


def check_versions(strict):
    import numpy, pandas, tokenizers, torch, transformers
    import huggingface_hub

    found = {
        "python": ".".join(map(str, sys.version_info[:3])),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "tokenizers": tokenizers.__version__,
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "huggingface_hub": huggingface_hub.__version__,
    }
    print("Dependencies")
    bad = []
    for k, want in EXPECTED.items():
        got = found[k]
        ok = got == want
        print(f"  {'ok ' if ok else 'DIF'} {k:<18} {got}" + ("" if ok else f"  (expected {want})"))
        if not ok:
            bad.append(k)
    if bad and strict:
        fail(f"versions differ: {', '.join(bad)} (use --no-strict-versions to go on)")

    print("\nGPU")
    if not torch.cuda.is_available():
        fail("torch.cuda.is_available() is False; MergeGen runs on the CPU, but the times "
             "of the study were measured on a GPU")
    cap = torch.cuda.get_device_capability(0)
    arch = torch.cuda.get_arch_list()
    print(f"  ok  device             {torch.cuda.get_device_name(0)} (sm_{cap[0]}{cap[1]})")
    print(f"  ok  CUDA of torch      {torch.version.cuda}")
    needed = f"sm_{cap[0]}{cap[1]}"
    if needed not in arch:
        fail(f"this build of torch has no kernels for {needed}; arch_list={arch}")
    print(f"  ok  {needed} in torch.cuda.get_arch_list()")

    # mergegen_inference._git_merge_single runs `git merge-file`.
    import subprocess
    try:
        v = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
        print(f"  ok  git (merge-file)   {v.stdout.strip()}")
    except Exception as e:
        fail(f"git not found on the PATH, and git merge-file needs it: {e}")


def run_fixture(backbone, checkpoint, reference):
    import torch
    from torch import nn
    from transformers import RobertaTokenizer, T5ForConditionalGeneration
    import mergegen_inference

    backbone = Path(backbone).expanduser().resolve()
    checkpoint = Path(checkpoint).expanduser().resolve()
    print("\nModel")
    for label, p in (("backbone", backbone), ("checkpoint", checkpoint)):
        if not p.exists():
            fail(f"{label} not found: {p}")
        print(f"  ok  {label:<16} {p}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = RobertaTokenizer.from_pretrained(str(backbone))
    tokenizer.add_tokens(["<lbra>", "<mbra>", "<rbra>"])

    class MergeT5(nn.Module):
        def __init__(self, model_type, tok):
            super().__init__()
            self.t5 = T5ForConditionalGeneration.from_pretrained(model_type)
            self.t5.resize_token_embeddings(len(tok))

    wrapper = MergeT5(str(backbone), tokenizer)
    try:
        wrapper.load_state_dict(torch.load(str(checkpoint), map_location=device))
    except RuntimeError as e:
        if "size mismatch" in str(e):
            fail("backbone and checkpoint do not match: the checkpoints of this study are "
                 "codet5-small (d_model=512)")
        raise
    print("  ok  state_dict loaded without size mismatch")

    tool = mergegen_inference.MergeInference.__new__(mergegen_inference.MergeInference)
    tool.tokenizer = tokenizer
    tool.device = device
    tool.model = wrapper.t5.to(device).eval()
    tool.max_conflict_length = 500
    tool.max_resolve_length = 200
    tool.num_beams = 3
    tool.lbra_token = "<lbra>"
    tool.rbra_token = "<rbra>"

    fixture = json.loads((HERE / "fixtures" / "smoke_conflicts.json").read_text())
    outputs = {}
    for rec in fixture:
        outputs[rec["chunk_id"]] = tool.generate_resolution(rec["all_raw_base"], rec["all_raw_a"], rec["all_raw_b"])
    digest = hashlib.sha256(json.dumps(outputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    print(f"\nInference over the {len(fixture)} conflicts of the fixture")
    ref = json.loads((HERE / "reference_digests.json").read_text())["digests"].get(reference)
    print(f"  computed    {digest}")
    print(f"  reference   {ref}")
    if ref is None:
        fail(f"reference_digests.json has no digest named '{reference}'")
    if digest != ref:
        fail("the environment loads, but its outputs differ from the reference. "
             "A dependency changed in a way that alters the output of the model.")
    print("  ok  outputs equal to the reference")
    return digest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--backbone", required=True, help="folder codet5-small-local")
    ap.add_argument("--checkpoint", required=True, help="trained checkpoint (best_model.pt)")
    ap.add_argument("--reference", required=True, help="name of the digest in reference_digests.json")
    ap.add_argument("--no-strict-versions", action="store_true", help="report version differences without stopping")
    args = ap.parse_args()

    check_versions(strict=not args.no_strict_versions)
    run_fixture(args.backbone, args.checkpoint, args.reference)
    print("\nEnvironment verified.")


if __name__ == "__main__":
    main()
