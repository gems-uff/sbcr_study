#!/bin/bash

# Create a folder called "data" if it doesn't exist
if [ ! -d "data" ]; then
    echo "Creating data directory..."
    mkdir data
fi

# Download the FSE2022 data and extract it into the "data/fse2022" folder
FSE2022_URL="https://zenodo.org/records/6366908/files/fse-2022-MergeBERT-data.tar.bz2?download=1"
FSE2022_DIR="data/fse2022"

echo "Downloading FSE2022 data..."
curl -L $FSE2022_URL -o fse2022_data.tar.bz2

echo "Extracting FSE2022 data..."
mkdir -p $FSE2022_DIR
tar -xjf fse2022_data.tar.bz2 -C $FSE2022_DIR

# Download the SBES2022 data and extract it into the "data/sbes2022" folder
SBES2022_URL="https://api.figshare.com/v2/file/download/48792520"
SBES2022_DIR="data/sbes2022"

echo "Downloading SBES2022 data..."
curl -L $SBES2022_URL -o $SBES2022_DIR/sbes2022_data.json

# Run the Python script to transform FSE2022 dataset
echo "Running FSE2022 dataset transformation..."
python3 transform_fse2022_dataset_for_ase2023.py

# Run the Python script to transform SBES2022 dataset
echo "Running SBES2022 dataset transformation..."
python3 transform_SBES2022_dataset_to_ase2023.py

echo "All tasks completed."
