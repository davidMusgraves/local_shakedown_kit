#!/bin/bash
set -e

echo "=== Dashboard Test Script ==="
echo "This script will run a quick 10-atom MD simulation with dashboard"
echo ""

# Activate environment
source venv/bin/activate
export CP2K_DATA_DIR=/opt/homebrew/share/cp2k/data

# Generate the 10-atom structure
echo "Generating 10-atom As4Se6 structure..."
python3 examples/make_as4se6_10.py

echo ""
echo "Running quick MD test with dashboard..."
echo "Expected: Dashboard should appear showing live MD metrics"
echo "Press 'q' to quit dashboard or 'c' to cancel run"
echo ""

# Run the quick test
python3 bin/run_cp2k.py inputs/md_quick_test.inp --project md_quick_test

echo ""
echo "=== Test Complete ==="
echo "Check md_quick_test.out for results"
