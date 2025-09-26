#!/usr/bin/env python3
import argparse, os, json, subprocess, sys, glob
from pathlib import Path

here = Path(__file__).resolve().parent
tools_dir = (here.parent / "tools").resolve()
sys.path.insert(0, str(tools_dir))

from parse_cp2k import parse_log

def first_or_none(patterns):
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None

if __name__=="__main__":
    ap=argparse.ArgumentParser(description="Evaluate a CP2K run (smoke-test).")
    ap.add_argument("project"); ap.add_argument("--dt_fs", type=float, default=0.5)
    a=ap.parse_args(); proj=a.project
    os.makedirs("reports", exist_ok=True)

    summary = {"project": proj}
    log_path = f"{proj}.out"
    summary["log"] = parse_log(log_path) if os.path.exists(log_path) else None

    # Robust discovery (covers multiple CP2K naming styles)
    pos = first_or_none([f"{proj}-pos-*.xyz", f"{proj}-POS-*.xyz", f"{proj}*-pos*.xyz", "*-pos-*.xyz"])
    vel = first_or_none([f"{proj}-vel-*.xyz", f"{proj}-VEL-*.xyz", f"{proj}*-vel*.xyz", "*-vel-*.xyz"])
    summary["pos_xyz"] = pos
    summary["vel_xyz"] = vel

    rdf_py  = str(tools_dir / "rdf.py")
    vdos_py = str(tools_dir / "vacf_vdos.py")

    if pos and os.path.exists(rdf_py):
        subprocess.run([sys.executable, rdf_py, pos, "--out", "reports/rdf.json"], check=False)
        summary["rdf_json"] = "reports/rdf.json"
    else:
        summary["rdf_json"] = None

    if vel and os.path.exists(vdos_py):
        subprocess.run([sys.executable, vdos_py, vel, "--dt_fs", str(a.dt_fs), "--out", "reports/vdos.json"], check=False)
        summary["vdos_json"] = "reports/vdos.json"
    else:
        summary["vdos_json"] = None

    with open("reports/run_summary.json","w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
