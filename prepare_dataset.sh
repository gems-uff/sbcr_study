#!/bin/bash

if [ ! -d "data" ]; then
    echo "Creating data directory..."
    mkdir data
fi

FSE2022_FILE="data/fse2022_data.tar.bz2"
SBES2022_FILE="data/sbes2022_data.json"
FSE2022_DIR="data/fse2022"

# Download the FSE2022 data if it doesn't already exist
if [ ! -f $FSE2022_FILE ]; then
    echo "Downloading FSE2022 data..."
    curl -L "https://zenodo.org/records/6366908/files/fse-2022-MergeBERT-data.tar.bz2?download=1" -o $FSE2022_FILE
else
    echo "FSE2022 data already exists. Skipping download."
fi

# Extract the FSE2022 data if the directory doesn't already exist
if [ ! -d $FSE2022_DIR ]; then
    echo "Extracting FSE2022 data..."
    tar -xjf $FSE2022_FILE -C data
else
    echo "FSE2022 data already extracted. Skipping extraction."
fi

# Download the SBES2022 data if it doesn't already exist
if [ ! -f $SBES2022_FILE ]; then
    echo "Downloading SBES2022 data..."
    curl -L "https://api.figshare.com/v2/file/download/48792520" -o $SBES2022_FILE
else
    echo "SBES2022 data already exists. Skipping download."
fi


echo "Running FSE2022 dataset transformation..."
python3 transform_fse2022_dataset_for_ase2023.py


echo "Running SBES2022 dataset transformation..."
python3 transform_SBES2022_dataset_to_ase2023.py

python3 filter_FSE_dataset.py

python3 separate_dataset.py

cd mergeGen
python3 run_total_dataset.py dataset1 dataset_parallel.py
python3 run_total_dataset.py dataset2 dataset_parallel.py
python3 run_total_dataset.py dataset2_Java dataset_parallel.py
python3 run_total_dataset.py dataset2_CSharp dataset_parallel.py
python3 run_total_dataset.py dataset2_JavaScript dataset_parallel.py
python3 run_total_dataset.py dataset2_TypeScript dataset_parallel.py
cd ..

echo "All tasks completed."
