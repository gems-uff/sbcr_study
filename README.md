
# Instructions:

1. Create a new conda environment
```sh
$ conda create -n sbcr_study python=3.8

$ conda activate sbcr_study

$ python -m pip install -r requirements.txt
```

2. Run the following script to prepare the datasets: `./prepare_dataset.sh`
    - Dataset1: SBES 2022 Dataset (https://doi.org/10.6084/m9.figshare.26831818) Paper: https://doi.org/10.1145/3555228.3555229
    - Dataset2: FSE 2022 Dataset (https://zenodo.org/records/6366908) Paper: https://doi.org/10.1145/3540250.354916

3. Prepare the data to be used by the MergeGen tool:
```sh
cd mergeGen
python run_total_dataset.py dataset1 dataset_parallel.py
python run_total_dataset.py dataset2 dataset_parallel.py
```
This script will pre-process the data from the two datasets, which is required by the MergeGen tool.

4. 
```sh
python run_mergegen.py dataset1 train
python run_mergegen.py dataset1 test
python run_mergegen.py dataset2 train
python run_mergegen.py dataset2 test
```