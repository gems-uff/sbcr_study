# Notice on the files derived from MergeGen

Five files of this folder derive from the code of MergeGen, published by Dong et al. with the paper "Merge Conflict Resolution: Classification or Generation?" (ASE 2023), in the repository [DJjjjhao/ase-merge](https://github.com/DJjjjhao/ase-merge) at commit [`0103f21`](https://github.com/DJjjjhao/ase-merge/tree/0103f21ea39c3719005917982d80628b148ec950):

| File | Relation to `ase-merge` |
|---|---|
| `run_mergegen.py` | Modified copy of `run_mergegen.py` |
| `dataset.py` | Modified copy of `dataset.py` |
| `dataset_parallel.py` | Modified copy of `dataset_parallel.py` |
| `run_total_dataset.py` | Modified copy of `runtotal_dataset.py` |
| `mergegen_inference.py` | Rebuilds the `MergeT5` wrapper of `run_mergegen.py` and follows the `git_merge` of `dataset_parallel.py` |

The original repository has no license. These five files are therefore not covered by the MIT license of this repository (see `LICENSE`), and no license is granted on them here. The changes made to them are: selection of the dataset by argument, the split read from an explicit file, the training seed read from the environment, the time of each test conflict, and the just-in-time inference path.

The trained models of the models archive are CodeT5-small weights fine-tuned with this code, and are distributed under the Apache 2.0 license of CodeT5-small (see `LICENSES.md` at the root).
