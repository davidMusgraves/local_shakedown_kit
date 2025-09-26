#!/usr/bin/env python3
import numpy as np, argparse

def random_pack(symbols, L, dmin=2.2, max_trials=200000):
    n=len(symbols); pos=np.zeros((n,3))
    for i in range(n):
        ok=False
        for _ in range(max_trials):
            cand=np.random.rand(3)*L
            if all(np.linalg.norm(cand-pos[j])>=dmin for j in range(i)):
                pos[i]=cand; ok=True; break
        if not ok: raise SystemExit("packing failed; reduce dmin or increase L")
    return pos

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--n_as', type=int, default=38)
    ap.add_argument('--n_se', type=int, default=58)
    ap.add_argument('--L', type=float, default=20.0)
    ap.add_argument('--out', default='inputs/as2se3_96_seed.xyz')
    a=ap.parse_args()
    syms=['As']*a.n_as + ['Se']*a.n_se
    pos=random_pack(syms, a.L, dmin=2.2)
    with open(a.out,'w') as f:
        f.write(f"{len(syms)}\nAs2Se3 ~96-atom random packed seed (PBC), L={a.L} Å\n")
        for s,(x,y,z) in zip(syms,pos):
            f.write(f"{s:2s} {x:10.5f} {y:10.5f} {z:10.5f}\n")
    print(a.out)
