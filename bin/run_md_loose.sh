#!/bin/bash
set -euo pipefail

PROJECT=md_loose_smear
LOGFILE="${PROJECT}.out"
INPUT="inputs/md_loose_smear.inp"
STRUCTURE="inputs/as4se6_10_seed.xyz"

if [[ ! -f "$STRUCTURE" ]]; then
  echo "Generating 10-atom structure..."
  python3 examples/make_as4se6_10.py
fi

: "${OMP_NUM_THREADS:=1}"
: "${MKL_NUM_THREADS:=1}"

if [[ ! -f "$INPUT" ]]; then
  echo "Input file $INPUT not found" >&2
  exit 1
fi

# start tailer
rm -f "$LOGFILE"
touch "$LOGFILE"

tail -n 100 -f "$LOGFILE" &
TAIL_PID=$!
trap "kill $TAIL_PID 2>/dev/null || true" EXIT

python3 bin/run_cp2k.py "$INPUT" --project "$PROJECT" --no-dashboard

kill $TAIL_PID 2>/dev/null || true
trap - EXIT

printf '\nMD run complete. Log: %s\n' "$LOGFILE"
printf 'Opening dashboard... (close Streamlit to return)\n'
python3 bin/view_dashboard.py "$LOGFILE" --input "$INPUT" --project "$PROJECT"
