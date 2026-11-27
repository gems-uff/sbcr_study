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

Section 3.3.2 of the paper gives the sizes of split 1 (its Table 2) and says that the other splits have test partitions of nearly the same size. The table gives the sizes of every split, in conflicts after the removal of exact duplicates, for all resolution categories and for the combination subset, on which SBCR is tuned and both approaches are evaluated. Dataset1 contains only combination conflicts. Splits 1 to 3 are grouped by merge. The project-disjoint split keeps all conflicts of a project in one partition. The chronological split leaves out the merges without a commit date and four merges of the test period that would each fill a large share of a test partition (one in Dataset1 and three in Dataset2C#), so its datasets hold fewer conflicts.

| Split | Dataset | Conflicts | Training | Validation | Test | Combination, training | Combination, validation | Combination, test |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Split 1 | Dataset1 | 5,490 | 4,392 | 549 | 549 | 4,392 | 549 | 549 |
| Split 1 | Dataset2Java | 57,628 | 46,101 | 5,763 | 5,764 | 13,739 | 1,717 | 1,719 |
| Split 1 | Dataset2C# | 16,316 | 13,052 | 1,627 | 1,637 | 4,366 | 547 | 545 |
| Split 1 | Dataset2JavaScript | 46,877 | 37,486 | 4,718 | 4,673 | 9,656 | 1,206 | 1,208 |
| Split 1 | Dataset2TypeScript | 11,511 | 9,208 | 1,152 | 1,151 | 3,133 | 392 | 392 |
| Split 2 | Dataset1 | 5,490 | 4,392 | 549 | 549 | 4,392 | 549 | 549 |
| Split 2 | Dataset2Java | 57,628 | 46,100 | 5,761 | 5,767 | 13,739 | 1,718 | 1,718 |
| Split 2 | Dataset2C# | 16,316 | 13,050 | 1,634 | 1,632 | 4,366 | 545 | 547 |
| Split 2 | Dataset2JavaScript | 46,877 | 37,455 | 4,791 | 4,631 | 9,656 | 1,207 | 1,207 |
| Split 2 | Dataset2TypeScript | 11,511 | 9,198 | 1,169 | 1,144 | 3,133 | 392 | 392 |
| Split 3 | Dataset1 | 5,490 | 4,394 | 548 | 548 | 4,394 | 548 | 548 |
| Split 3 | Dataset2Java | 57,628 | 46,104 | 5,762 | 5,762 | 13,738 | 1,720 | 1,717 |
| Split 3 | Dataset2C# | 16,316 | 13,055 | 1,629 | 1,632 | 4,366 | 545 | 547 |
| Split 3 | Dataset2JavaScript | 46,877 | 37,489 | 4,723 | 4,665 | 9,655 | 1,216 | 1,199 |
| Split 3 | Dataset2TypeScript | 11,511 | 9,206 | 1,151 | 1,154 | 3,133 | 392 | 392 |
| Project-disjoint | Dataset1 | 5,490 | 4,392 | 549 | 549 | 4,392 | 549 | 549 |
| Project-disjoint | Dataset2Java | 57,628 | 46,103 | 5,763 | 5,762 | 13,740 | 1,718 | 1,717 |
| Project-disjoint | Dataset2C# | 16,316 | 13,052 | 1,632 | 1,632 | 4,366 | 546 | 546 |
| Project-disjoint | Dataset2JavaScript | 46,877 | 37,501 | 4,688 | 4,688 | 9,656 | 1,207 | 1,207 |
| Project-disjoint | Dataset2TypeScript | 11,511 | 9,208 | 1,152 | 1,151 | 3,133 | 392 | 392 |
| Chronological | Dataset1 | 5,166 | 4,063 | 550 | 553 | 4,063 | 550 | 553 |
| Chronological | Dataset2Java | 56,182 | 44,410 | 6,746 | 5,026 | 13,325 | 1,717 | 1,721 |
| Chronological | Dataset2C# | 14,671 | 11,280 | 1,772 | 1,619 | 3,888 | 546 | 546 |
| Chronological | Dataset2JavaScript | 45,734 | 38,036 | 3,923 | 3,775 | 9,312 | 1,207 | 1,206 |
| Chronological | Dataset2TypeScript | 11,324 | 9,065 | 1,263 | 996 | 3,064 | 392 | 392 |

Script: `analysis/datasets/partition_sizes.py`, run on the archives with `--root partition-1`, `partition-2` and `partition-3`, `--root split-comparison --arm pd` for the project-disjoint split, and `--root chronological --arm mg`. Each run writes `partition_sizes.csv` in its root and prints the table, with the number of groups of each partition. The rows of split 1 are those of Table 2 of the paper.
