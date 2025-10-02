#!/bin/bash
set -euo pipefail

PHASE1_INPUT="inputs/as40se60_phase1.inp"
PHASE2_INPUT="inputs/as40se60_phase2_ot.inp"
PHASE1_PROJECT="as40se60_phase1"
PHASE2_PROJECT="as40se60_phase2"
PHASE1_LOG="${PHASE1_PROJECT}.out"
PHASE2_LOG="${PHASE2_PROJECT}.out"

: "${OMP_NUM_THREADS:=1}"
: "${MKL_NUM_THREADS:=1}"

if [[ ! -f "$PHASE1_INPUT" ]]; then
  echo "Missing $PHASE1_INPUT" >&2
  exit 1
fi
if [[ ! -f "$PHASE2_INPUT" ]]; then
  echo "Missing $PHASE2_INPUT" >&2
  exit 1
fi

rm -f "$PHASE1_LOG" "$PHASE2_LOG"
touch "$PHASE1_LOG" "$PHASE2_LOG"

run_cp2k () {
  local input=$1
  local project=$2
  local logfile=$3

  tail -n 100 -f "$logfile" &
  local tail_pid=$!
  trap "kill $tail_pid 2>/dev/null || true" RETURN

  python3 bin/run_cp2k.py "$input" --project "$project" --no-dashboard

  kill $tail_pid 2>/dev/null || true
}

run_cp2k "$PHASE1_INPUT" "$PHASE1_PROJECT" "$PHASE1_LOG"

PHASE1_RESTART="${PHASE1_PROJECT}-1.restart"
PHASE1_WFN="${PHASE1_PROJECT}-RESTART.wfn"
if [[ ! -f "$PHASE1_RESTART" ]]; then
  echo "Missing restart file $PHASE1_RESTART" >&2
  exit 1
fi

if [[ ! -f "$PHASE1_WFN" ]]; then
  echo "Missing wavefunction file $PHASE1_WFN" >&2
  exit 1
fi

export CP2K_RESTART_FILE="$PHASE1_RESTART"
export CP2K_WFN_RESTART="$PHASE1_WFN"

run_cp2k "$PHASE2_INPUT" "$PHASE2_PROJECT" "$PHASE2_LOG"

echo "\nPhase 1 log: $PHASE1_LOG"
echo "Phase 2 log: $PHASE2_LOG"
