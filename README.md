# Local Shakedown Kit (CP2K + Evaluators)

This kit lets you run *local* smoke tests of CP2K and sanity-check outputs before moving to Rescale.

## Quick start
```bash
# (optional) create env for the Python evaluators
conda env create -f env/chalcogenide-local.yml
conda activate geasse-local

# Single-point smoke
python bin/run_cp2k.py inputs/sp_smoke.inp --project sp_smoke
python bin/eval_run.py sp_smoke

# Short MD smoke (trajectory + velocities)
python bin/run_cp2k.py inputs/md_smoke.inp --project md_smoke
python bin/eval_run.py md_smoke

# Optional: HSE06/ADMM plumbing test
python bin/run_cp2k.py inputs/hse06_sp_template.inp --project hse_smoke
```

Pass criteria (suggested): `return_code==0`, `scf_cycles_mean < ~12`, `temperature_mean≈300 K` with std < ~50 K.
Artifacts land in `reports/` (summary JSON, RDF, VDOS).

## Requirements
- CP2K v9.x on PATH (e.g., `cp2k.psmp`), and `CP2K_DATA_DIR` set to directory with `BASIS_MOLOPT`, `GTH_POTENTIALS`, `dftd3.dat`.
- The inputs use PBE-D3 and DZVP-MOLOPT-SR-GTH for speed; `hse06_sp_template.inp` enables ADMM (fill `AUX_FIT` to match your build).

## Folder map
- `inputs/`  : tiny CP2K inputs + toy As2Se3 cluster.
- `bin/`     : runner + evaluator.
- `tools/`   : parsers and quick analyses (log stats, RDF, VDOS, KK stub).
- `examples/`: simple generators for toy structures (ASE-based seed maker included).
- `reports/` : output summaries and plots.
