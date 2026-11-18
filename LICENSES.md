# Licenses

| What | License |
|---|---|
| The code of this repository | MIT (`LICENSE`), except the five files below |
| `mergegen/run_mergegen.py`, `dataset.py`, `dataset_parallel.py`, `run_total_dataset.py`, `mergegen_inference.py` | None granted: they derive from the code of MergeGen, which has no license (`mergegen/NOTICE.md`) |
| The datasets and results archives | CC BY 4.0 |
| The models archive | Apache 2.0, the license of CodeT5-small |
| The RQ4 archive | CC BY 4.0 |

## Sources of the data

The datasets and results archives are adapted from two datasets under CC BY 4.0:

- **Dataset1**: "Merge conflicts dataset used in SBES 2022 paper", by Heleno de Souza Campos Junior and Gleiph Ghiotto L. de Menezes, FigShare, [10.6084/m9.figshare.26831818.v4](https://doi.org/10.6084/m9.figshare.26831818.v4), CC BY 4.0. The archives carry the 6,269 chunks of its `dataset_processed_base.json` in the format of this study, without the exact duplicates, and their splits.
- **Dataset2**: "Data set for FSE 2022 Submission Program Merge Conflict Resolution via Neural Transformers", Zenodo, [10.5281/zenodo.6366908](https://doi.org/10.5281/zenodo.6366908), CC BY 4.0, the data of Svyatkovskiy et al., "Program Merge Conflict Resolution via Neural Transformers" (ESEC/FSE 2022). The archives carry its conflicts in the format of this study, filtered to those resolved by combination for SBCR, without the exact duplicates, and their splits.

The conflicts of both datasets, and the RQ4 packages built from them, hold fragments of the code of open-source projects, which keep the licenses of those projects. CC BY 4.0 applies to what this study adds: the selection, the splits, the labels and the results.

## The models archive

The checkpoints are [CodeT5-small](https://huggingface.co/Salesforce/codet5-small) (Wang et al., "CodeT5: Identifier-aware Unified Pre-trained Encoder-Decoder Models for Code Understanding and Generation", EMNLP 2021), released under the Apache License 2.0, fine-tuned with the MergeGen code of this repository on Dataset1 and on each language of Dataset2 (above). The archive carries the text of the Apache License 2.0 and states the change: the weights are those of CodeT5-small after fine-tuning, with the embedding table enlarged for the three structural tokens of MergeGen.

## Anaconda's `defaults` channel

Recreating the environments `mergegen-repl`, `mergegen-train` and `sbcr-analysis`, or building the analysis image, downloads packages of Anaconda's `defaults` channel under the [Anaconda Terms of Service](https://www.anaconda.com/legal/terms/terms-of-service): free for individuals, for universities, for non-profit and research organizations, and for for-profit organizations of up to 200 people, and paid above that (`environments/README.md`).
