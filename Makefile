SHELL := /bin/bash

PY := python3
CP2K ?= $(shell command -v cp2k.psmp || command -v cp2k)

.PHONY: sp md sp_fast md_fast eval clean

sp:
	$(PY) bin/run_cp2k.py --mode sp --profile compat --project sp_smoke_compat
	$(PY) bin/eval_run.py sp_smoke_compat

md:
	$(PY) bin/run_cp2k.py --mode md --profile compat --project md_smoke_compat
	$(PY) bin/eval_run.py md_smoke_compat

sp_fast:
	$(PY) bin/run_cp2k.py --mode sp --profile fast --project sp_smoke_fast

md_fast:
	$(PY) bin/run_cp2k.py --mode md --profile fast --project md_smoke_fast

eval:
	$(PY) bin/eval_run.py $(proj)

clean:
	rm -f *.out *.restart* *-RESTART.wfn* *-pos-*.xyz *-vel-*.xyz
	rm -rf reports/*