#!/usr/bin/env python3
import argparse, os, json, subprocess, sys, glob, math
from pathlib import Path

here = Path(__file__).resolve().parent
tools_dir = (here.parent / "tools").resolve()
sys.path.insert(0, str(tools_dir))

from parse_cp2k import parse_log

# Physical constants
BOHR_A = 0.529177210903  # Angstrom
AU_TIME_FS = 0.024188843265857  # fs
ANG_PER_FS_TO_M_PER_S = 1.0e5   # 1 Å/fs = 1e5 m/s
AMU_KG = 1.66053906660e-27
KB = 1.380649e-23
MASSES = {"H":1.00784,"C":12.0107,"N":14.0067,"O":15.999,"Si":28.085,"Ge":72.630,"As":74.921595,"Se":78.971}

def first_or_none(patterns):
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None

def read_vel_xyz(path):
    frames=[]; species=None
    with open(path,"r") as f:
        while True:
            line=f.readline()
            if not line: break
            n=int(line.strip()); _=f.readline()
            cr=[]; sp=[]
            for _ in range(n):
                parts=f.readline().split()
                sp.append(parts[0]); cr.append([float(parts[1]),float(parts[2]),float(parts[3])])
            if species is None: species=sp
            frames.append(cr)
    return species, frames

def derive_temperature_from_vel(vel_xyz_path):
    if not os.path.exists(vel_xyz_path): return None
    species, frames = read_vel_xyz(vel_xyz_path)
    if not frames: return None
    conv = (BOHR_A / AU_TIME_FS) * ANG_PER_FS_TO_M_PER_S  # m/s per (bohr/au_t)
    m = [MASSES.get(s, None) for s in species]
    if any(x is None for x in m): return None
    m = [x * AMU_KG for x in m]  # kg
    temps=[]
    for V in frames:
        KE = 0.0
        for (vx,vy,vz), mi in zip(V, m):
            v2 = (vx*conv)**2 + (vy*conv)**2 + (vz*conv)**2
            KE += 0.5 * mi * v2
        N = len(V)
        T = (2.0 * KE) / (3.0 * N * KB)
        temps.append(T)
    if not temps: return None
    mean = sum(temps)/len(temps)
    var = sum((t-mean)*(t-mean) for t in temps)/len(temps)
    return {"temperature_from_vel_mean": mean, "temperature_from_vel_std": math.sqrt(var)}

if __name__=="__main__":
    ap=argparse.ArgumentParser(description="Evaluate a CP2K run (smoke-test).")
    ap.add_argument("project"); ap.add_argument("--dt_fs",type=float,default=0.5)
    a=ap.parse_args(); proj=a.project
    os.makedirs("reports", exist_ok=True)

    summary={"project":proj}
    log_path = f"{proj}.out"
    summary["log"] = parse_log(log_path) if os.path.exists(log_path) else None

    pos = first_or_none([f"{proj}-pos-*.xyz", f"{proj}-POS-*.xyz", f"{proj}*-pos*.xyz", "*-pos-*.xyz"])
    vel = first_or_none([f"{proj}-vel-*.xyz", f"{proj}-VEL-*.xyz", f"{proj}*-vel*.xyz", "*-vel-*.xyz"])
    summary["pos_xyz"] = pos; summary["vel_xyz"] = vel

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

    derived = derive_temperature_from_vel(vel) if vel else None
    summary["derived_temperature"] = derived
    if summary.get("log") is None: summary["log"] = {}
    if derived:
        summary["log"].setdefault("temperature_mean", derived["temperature_from_vel_mean"])
        summary["log"].setdefault("temperature_std",  derived["temperature_from_vel_std"])

    with open("reports/run_summary.json","w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))