#!/bin/bash
echo "Starting PrintQue API..."

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run ./install.sh first."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Start the Flask app
python app.py
