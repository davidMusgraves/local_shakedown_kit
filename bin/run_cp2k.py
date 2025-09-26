#!/usr/bin/env python3
import argparse, os, subprocess, json, pathlib

def which(p): 
    for d in os.environ.get("PATH","").split(os.pathsep):
        f=os.path.join(d,p)
        if os.path.isfile(f) and os.access(f,os.X_OK): return f
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("inp"); ap.add_argument("--project"); ap.add_argument("--cp2k")
    a=ap.parse_args()
    cp2k = a.cp2k or which("cp2k.psmp") or which("cp2k")
    if not cp2k: raise SystemExit("cp2k not found on PATH")
    env=os.environ.copy()
    env["PROJECT"]=a.project or pathlib.Path(a.inp).stem
    out=f"{env['PROJECT']}.out"
    with open(out,"w") as fout:
        p=subprocess.Popen([cp2k,"-i",a.inp],stdout=fout,stderr=subprocess.STDOUT,env=env)
        rc=p.wait()
    print(json.dumps({"project":env["PROJECT"],"logfile":out,"return_code":rc}))

if __name__=="__main__": main()