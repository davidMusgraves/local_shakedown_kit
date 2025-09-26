#!/usr/bin/env python3
import argparse, os, subprocess, json, pathlib, sys

def which(p):
    for d in os.environ.get("PATH","").split(os.pathsep):
        f=os.path.join(d,p)
        if os.path.isfile(f) and os.access(f,os.X_OK): return f
    return None

def default_inp(mode, profile):
    return f"inputs/{mode}_smoke_{profile}.inp"

def main():
    ap=argparse.ArgumentParser(description="Run CP2K with profiles or explicit input path.")
    ap.add_argument("inp", nargs="?", help="Explicit input file (optional if --mode/--profile given)")
    ap.add_argument("--mode", choices=["sp","md"], help="Smoke test mode (sp|md)")
    ap.add_argument("--profile", choices=["compat","fast"], default="compat", help="Input profile")
    ap.add_argument("--project", help="CP2K PROJECT name")
    ap.add_argument("--cp2k", help="Path to cp2k executable (cp2k.psmp or cp2k)")
    a=ap.parse_args()

    inp = a.inp or (default_inp(a.mode, a.profile) if a.mode else None)
    if not inp:
        ap.error("Provide an input file or --mode with --profile")

    cp2k = a.cp2k or which("cp2k.psmp") or which("cp2k")
    if not cp2k:
        raise SystemExit("cp2k not found on PATH")

    env=os.environ.copy()
    env["PROJECT"]=a.project or pathlib.Path(inp).stem
    out=f"{env['PROJECT']}.out"
    with open(out,"w") as fout:
        p=subprocess.Popen([cp2k,"-i",inp],stdout=fout,stderr=subprocess.STDOUT,env=env)
        rc=p.wait()
    print(json.dumps({"project":env["PROJECT"],"logfile":out,"return_code":rc}))

if __name__=="__main__":
    sys.exit(main())