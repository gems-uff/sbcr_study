#!/bin/bash

LOGS_DIR="LOGS"

if [ ! -d "data" ]; then
    echo "Creating data directory..."
    mkdir data
fi

# Check if LOGS_DIR exists, if not, create it
if [ ! -d $LOGS_DIR ]; then
    echo "Creating LOGS directory..."
    mkdir $LOGS_DIR
fi

FSE2022_FILE="data/fse2022_data.tar.bz2"
SBES2022_FILE="data/sbes2022_data.json"
FSE2022_DIR="data/fse2022"

{

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
    curl -L "https://api.figshare.com/v2/file/download/49875561" -o $SBES2022_FILE
else
    echo "SBES2022 data already exists. Skipping download."
fi


} | tee -a $LOGS_DIR/download_datasets.txt



echo "Running FSE2022 dataset transformation..."
python3 transform_fse2022_dataset_for_ase2023.py 2>&1 | tee $LOGS_DIR/transform_fse2022_dataset_for_ase2023.txt


echo "Running SBES2022 dataset transformation..."
python3 transform_SBES2022_dataset_to_ase2023.py 2>&1 | tee $LOGS_DIR/transform_SBES2022_dataset_to_ase2023.txt

python3 filter_FSE_dataset.py 2>&1 | tee $LOGS_DIR/filter_FSE_dataset.txt

python3 separate_datasets.py 2>&1 | tee $LOGS_DIR/separate_datasets.txt

python3 extract_combination_on_separated_datasets.py 2>&1 | tee $LOGS_DIR/extract_combination_on_separated_datasets.txt

cd mergeGen

{

python3 run_total_dataset.py dataset1 dataset_parallel.py
python3 run_total_dataset.py dataset2 dataset_parallel.py
python3 run_total_dataset.py dataset2_Java dataset_parallel.py
python3 run_total_dataset.py dataset2_CSharp dataset_parallel.py
python3 run_total_dataset.py dataset2_JavaScript dataset_parallel.py
python3 run_total_dataset.py dataset2_TypeScript dataset_parallel.py

} | tee -a $LOGS_DIR/proccess_mergegen_data.txt
cd ..

echo "All tasks completed."
