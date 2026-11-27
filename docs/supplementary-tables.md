# Tables that complement the paper

These tables give counts that the paper describes without listing them. Each comes from a script of this repository run on the archives, named under the table.

## Exclusions from the source of Dataset1

Section 3.3.1 of the paper names the rules that take Dataset1 from the 13,573 chunks of its public source, the SBES 2022 dataset on FigShare (`dataset.json`), to the 6,269 chunks of the study. The table gives the chunks each rule removes, in the order the scripts of the earlier study apply them: the reconstruction of the base version (`find_base.py`) first, then the separation of the resolution from its context (`get_clean_solution` of `transform_sbes2022_dataset.py`).

| Step | Removed | Left |
|---|---:|---:|
| Source (`dataset.json`) | | 13,573 |
| 1. A version of 20,000 characters or more, which the reconstruction of the base does not search | 170 | 13,403 |
| 2. The region of the conflict not located at a single position of the base file | 6,119 | 7,284 |
| 3. The region located, but empty | 208 | 7,076 |
| 4. The context lines of the resolution do not match those of the chunk | 807 | 6,269 |

The set of chunks removed does not depend on the order of the two rules, but the count of each step does. With the context check first, it removes 2,780 chunks, and the reconstruction of the base then removes 16, 4,333 and 175 in steps 1 to 3, again leaving the 6,269.

Script: `preparation/dataset1/dataset1_trace.py`, output in `dataset1-trace/` of the Results archive.

## Partition sizes of every split

PARTITION_SIZES_PENDING
