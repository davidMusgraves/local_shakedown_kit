# Test Shakedown (compat + fast)

**Goal:** Run the local shakedown kit end-to-end and surface a pass/fail summary.

## Preflight
- Ensure CP2K is on PATH (`cp2k.psmp` or `cp2k`) and `CP2K_DATA_DIR` is set.
- Activate your Python venv if you use one.

## Run (compat profile)
```bash
unset MallocStackLogging MallocStackLoggingNoCompact
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export CP2K_LAUNCH="mpirun -np 6"
make sp
make md
bash bin/doctor.sh md_smoke_compat
```
