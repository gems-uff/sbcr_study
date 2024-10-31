#!/bin/bash

LOGS_DIR="LOGS"

# Check if LOGS_DIR exists, if not, create it
if [ ! -d $LOGS_DIR ]; then
    echo "Creating LOGS directory"
    mkdir $LOGS_DIR
fi


{
python3 collect_dataset_stats.py dataset1_complete
python3 collect_dataset_stats.py dataset2_complete
python3 collect_dataset_stats.py dataset2_Java_complete
python3 collect_dataset_stats.py dataset2_CSharp_complete
python3 collect_dataset_stats.py dataset2_JavaScript_complete
python3 collect_dataset_stats.py dataset2_TypeScript_complete
} | tee -a $LOGS_DIR/datasets_stats_collection.txt

echo "All stats collected."