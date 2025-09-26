#!/usr/bin/env python3
import re, json, sys

ENERGY_PATTERNS=[r"Total FORCE_EVAL\s*\(\s*QS\s*\)\s*energy\s*=\s*([-\d\.Ee\+]+)", r"Total energy:\s*([-\d\.Ee\+]+)"]
TEMP_PATTERNS=[r"Temperature\s*\[K\]\s*:\s*([-\d\.Ee\+]+)", r"TEMPERATURE\s+([-\d\.Ee\+]+)", r"Temperature:\s*([-\d\.Ee\+]+)"]
SCF_PATTERNS=[r"SCF run converged in\s*(\d+)\s*steps", r"Step\s*(\d+)\s*.*?Convergence"]

def grep_all(pats, txt, cast=float):
    out=[]; import re
    for p in pats:
        for m in re.finditer(p, txt, flags=re.IGNORECASE): out.append(cast(m.group(1)))
    return out

def parse_log(path):
    try: txt=open(path,"r",errors="ignore").read()
    except: return {"energies":[],"temperatures":[],"scf_cycles":[],"temperature_mean":None,"temperature_std":None,"scf_cycles_mean":None}
    e=grep_all(ENERGY_PATTERNS,txt,float); t=grep_all(TEMP_PATTERNS,txt,float); s=grep_all(SCF_PATTERNS,txt,int)
    tmean=sum(t)/len(t) if t else None
    tstd=(sum((x-tmean)**2 for x in t)/len(t))**0.5 if t else None
    smean=sum(s)/len(s) if s else None
    return {"energies":e,"temperatures":t,"scf_cycles":s,"temperature_mean":tmean,"temperature_std":tstd,"scf_cycles_mean":smean}

if __name__=="__main__":
    print(json.dumps(parse_log(sys.argv[1] if len(sys.argv)>1 else ""), indent=2))