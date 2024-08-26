
Instructions:

1. Run the following script to download the datasets: `./download_data.sh`
    - FSE 2022 Dataset (https://zenodo.org/records/6366908) Paper: https://doi.org/10.1145/3540250.354916
    - SBES 2022 Dataset (https://doi.org/10.6084/m9.figshare.26831818) Paper: https://doi.org/10.1145/3555228.3555229
2. Run the following script to separate the datasets: `python separate_datasets.py`
Given the two dataset files, randomizes the conflicts and generates the following files:
dataset1_training.json
dataset1_validation.json
dataset1_testing.json
dataset2_training.json
dataset2_validation.json
dataset2_testing.json

2. Generate the processed files needed by MergeGen approach
