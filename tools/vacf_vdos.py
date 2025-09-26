import numpy as np, json, os

def read_vel_xyz(path):
    frames=[]; species=None
    with open(path,"r") as f:
        while True:
            line=f.readline()
            if not line: break
            n=int(line.strip())
            _=f.readline()
            cr=[]; sp=[]
            for _ in range(n):
                parts=f.readline().split()
                sp.append(parts[0]); cr.append([float(parts[1]),float(parts[2]),float(parts[3])])
            if species is None: species=sp
            frames.append(np.array(cr))
    return species, np.array(frames)

def vacf(vels):
    v0=vels[0]
    ac=[]
    for t in range(len(vels)):
        ac.append(np.mean(np.sum(vels[t]*v0,axis=1)))
    ac=np.array(ac)
    return ac/ac[0] if ac[0]!=0 else ac

def vdos_from_vacf(ac, dt_fs):
    spec=np.abs(np.fft.rfft(ac))
    freq=np.fft.rfftfreq(len(ac), d=dt_fs*1e-15)
    cm1 = freq/3e10
    return cm1, (spec/np.max(spec) if np.max(spec)>0 else spec)

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("vel_xyz")
    ap.add_argument("--dt_fs", type=float, default=0.5)
    ap.add_argument("--out", default="reports/vdos.json")
    a=ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    _,vels = read_vel_xyz(a.vel_xyz)
    ac = vacf(vels)
    cm1, vdos = vdos_from_vacf(ac, a.dt_fs)
    with open(a.out,"w") as f: json.dump({"cm-1": cm1.tolist(), "vdos": vdos.tolist()}, f, indent=2)
    print(a.out)
