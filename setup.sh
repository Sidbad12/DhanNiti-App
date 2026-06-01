#!/bin/bash
# setup.sh — DhanNiti Launcher

# Check if Python is installed
if ! command -v python3 &> /dev/null
then
    echo "python3 is not installed or not in PATH."
    exit 1
fi

# Run the python installer script
python3 setup.py
