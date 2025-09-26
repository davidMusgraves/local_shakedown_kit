.PHONY: smoke md hse eval_sp eval_md clean

smoke:
	python bin/run_cp2k.py inputs/sp_smoke.inp --project sp_smoke
	python bin/eval_run.py sp_smoke

md:
	python bin/run_cp2k.py inputs/md_smoke.inp --project md_smoke
	python bin/eval_run.py md_smoke

hse:
	python bin/run_cp2k.py inputs/hse06_sp_template.inp --project hse_smoke

eval_sp:
	python bin/eval_run.py sp_smoke

eval_md:
	python bin/eval_run.py md_smoke

clean:
	rm -f *.out *.restart *-pos-*.xyz *-vel-*.xyz *-RESTART.wfn
	rm -rf reports/*
