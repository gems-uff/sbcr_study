#!/bin/bash

LOGS_DIR="LOGS"
cd mergeGen
# MAX_RESOLVE_LENGTH=100

# Check if LOGS_DIR exists, if not, create it
if [ ! -d $LOGS_DIR ]; then
    echo "Creating LOGS directory"
    mkdir $LOGS_DIR
fi

# Time each command and log the time taken
{
    echo "Extracting for dataset1 model dataset1..."
    python3 extract_mergeGen_similarities.py dataset1 dataset1 $MAX_RESOLVE_LENGTH 2>&1 | tee $LOGS_DIR/dataset1_model_dataset1_similarities.txt
    echo "Extracting for dataset1 model dataset_Java..."
    python3 extract_mergeGen_similarities.py dataset1 dataset2_Java $MAX_RESOLVE_LENGTH 2>&1 | tee $LOGS_DIR/dataset1_model_dataset2_similarities.txt
    
    echo "Extracting for dataset2_Java model dataset1..."
    python3 extract_mergeGen_similarities.py dataset2_Java dataset1 $MAX_RESOLVE_LENGTH 2>&1 | tee $LOGS_DIR/dataset2_Java_model_dataset1_similarities.txt
    echo "Extracting for dataset2_Java model dataset2_Java..."
    python3 extract_mergeGen_similarities.py dataset2_Java dataset2_Java $MAX_RESOLVE_LENGTH 2>&1 | tee $LOGS_DIR/dataset2_Java_model_dataset2_similarities.txt
    
    echo "Extracting for dataset2_CSharp model dataset2_CSharp..."
    python3 extract_mergeGen_similarities.py dataset2_CSharp dataset2_CSharp $MAX_RESOLVE_LENGTH 2>&1 | tee $LOGS_DIR/dataset2_CSharp_model_dataset2_similarities.txt

    echo "Extracting for dataset2_JavaScript model dataset2_JavaScript..."
    python3 extract_mergeGen_similarities.py dataset2_JavaScript dataset2_JavaScript $MAX_RESOLVE_LENGTH 2>&1 | tee $LOGS_DIR/dataset2_JavaScript_model_dataset2_similarities.txt

    echo "Extracting for dataset2_TypeScript model dataset2_TypeScript..."
    python3 extract_mergeGen_similarities.py dataset2_TypeScript dataset2_TypeScript $MAX_RESOLVE_LENGTH 2>&1 | tee $LOGS_DIR/dataset2_TypeScript_model_dataset2_similarities.txt

} | tee -a $LOGS_DIR/all_mergeGen_similarities.txt


echo "All mergeGen similarities tasks completed."