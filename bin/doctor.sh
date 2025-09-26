#!/usr/bin/env bash
set -e
proj="$1"
echo "== Doctor for project: $proj =="
ls -l "${proj}.out" || true
ls -l ${proj}-pos-*.xyz 2>/dev/null || echo "no pos xyz found"
ls -l ${proj}-vel-*.xyz 2>/dev/null || echo "no vel xyz found"
python bin/eval_run.py "$proj" || true
echo "== Done =="
