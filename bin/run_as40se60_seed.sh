#!/bin/bash
set -euo pipefail

PROJECT=as40se60_melt
LOGFILE="${PROJECT}.out"
INPUT="inputs/md_as40se60_melt.inp"
STRUCTURE="inputs/as40se60_100_seed.xyz"

: "${OMP_NUM_THREADS:=1}"
: "${MKL_NUM_THREADS:=1}"

if [[ ! -f "$STRUCTURE" ]]; then
  echo "Generating As40Se60 100-atom seed structure..."
  python3 examples/make_as40se60_100.py
fi

rm -f "$LOGFILE"
touch "$LOGFILE"

tail -n 100 -f "$LOGFILE" &
TAIL_PID=$!
trap "kill $TAIL_PID 2>/dev/null || true" EXIT

python3 bin/run_cp2k.py "$INPUT" --project "$PROJECT" --no-dashboard

kill $TAIL_PID 2>/dev/null || true
trap - EXIT

echo "\nMelt stage finished. Log: $LOGFILE"
echo "Launching dashboard... (close Streamlit when done)"
python3 bin/view_dashboard.py "$LOGFILE" --input "$INPUT" --project "$PROJECT"
