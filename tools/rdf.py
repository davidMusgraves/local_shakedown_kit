#!/usr/bin/env python3
import numpy as np, json, os

def read_xyz_traj(path):
    frames = []
    with open(path,"r") as f:
        while True:
            nline = f.readline()
            if not nline: break
            n = int(nline.strip())
            _ = f.readline()
            species=[]; coords=[]
            for _ in range(n):
                parts=f.readline().split()
                if len(parts)<4: return frames
                species.append(parts[0])
                coords.append([float(parts[1]),float(parts[2]),float(parts[3])])
            frames.append((np.array(species), np.array(coords)))
    return frames

def compute_rdf(frames, pairs=(("As","Se"),("Se","Se"),("As","As")), rmax=6.0, nbins=200):
    hist = {pair: np.zeros(nbins) for pair in pairs}
    dr = rmax/nbins
    for species, coords in frames:
        for i in range(len(coords)):
            for j in range(i+1,len(coords)):
                r = np.linalg.norm(coords[j]-coords[i])
                if r<rmax:
                    a,b = species[i], species[j]
                    key = (a,b) if (a,b) in hist else (b,a) if (b,a) in hist else None
                    if key is not None:
                        hist[key][int(r/dr)] += 2
    rgrid = np.linspace(dr/2, rmax-dr/2, nbins)
    out = {}
    for pair, h in hist.items():
        key = f"{pair[0]}-{pair[1]}"
        out[key] = {"r": rgrid.tolist(), "g_r": (h/np.max(h) if np.max(h)>0 else h).tolist()}
    return out

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("xyz")
    ap.add_argument("--out", default="reports/rdf.json")
    a=ap.parse_args()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    frames = read_xyz_traj(a.xyz)
    res = compute_rdf(frames)
    with open(a.out,"w") as f: json.dump(res,f,indent=2)
    print(a.out)