# As-Se / Ge-Se Optical Workflow Plan

**Goal:** Generate validated amorphous structures and optical properties across the mean coordination r_mean ~ 2.2-2.7, ready for local shakedown runs and scaling to Rescale.
**Last updated:** 2025-09-25

## 0. Scope and Targets
- Focus on compositions bracketing the rigidity percolation window (r_mean ~ 2.3-2.5) where structure and optics vary sharply.
- Anchor points: As2Se3 (r_mean = 2.4), GeSe4 (20% Ge, r_mean = 2.4), GeSe2 (r_mean ~ 2.67) to probe the blue edge.
- Include ternary cut Se60Ge40-xAsx (x = 0-25) with special attention to x ~ 5, where experiments show maxima in Tg, transmittance, band gap, and Urbach energy.
- Per composition deliverables: relaxed amorphous cells; structure factors and RDFs with partials; homopolar fractions and motif statistics; VDOS and IR absorption; electronic DOS and band edges (HSE06 baseline, GW spot checks); epsilon2(omega), n(omega), k(omega) assembled from vibrational and electronic pieces.

## 1. Build Realistic Amorphous Seeds
1. **Large-cell sampling (classical or ML) to produce seeds**
   - Follow Mauro-style multiscale strategy: fit or reuse high-quality potentials (two-body plus angular terms) trained on ab initio data.
   - Optionally train a compact GAP or MACE model on available DFT snippets to melt-quench 1k-3k atom boxes efficiently.
2. **Seed acceptance gates before DFT**
   - Match homopolar fractions versus r_mean (Ge-Ge and Se-Se content trends from Mauro's Ge-Se work).
   - Reproduce the rigidity window in As-Se (threshold around r_mean 2.3-2.4) and monitor soft-mode fraction trends.
   - Capture medium-range order signatures such as the 3.02 A second peak in GeSe2 and homopolar bond fractions (~4%).
3. **Benchmark against experiment when possible**
   - Compare RDF and S(Q) to Petri/Salmon neutron or X-ray data; use reverse Monte Carlo refinement if experimental curves are provided.
   - Validate densities against measured values for each composition.
4. **Down-select to CP2K-ready cells**
   - Choose 240-480 atom supercells preserving key motifs (corner/edge-sharing Ge(Se1/2)4 tetrahedra, As pyramids, homopolar content, ring statistics).
   - Carry seed bond-type and ring distributions through to the DFT melt-quench stage.

## 2. CP2K Melt-Quench and Relaxation (PBE-D3 Baseline)
- Use CP2K v9.1 (cp2k.psmp) with GPW/Quickstep; track version in inputs for reproducibility.
- Pseudopotentials and bases: GTH-PBE with MOLOPT or MOLOPT-SR; include AUX/ADMM bases needed for later HSE06.
- SCF: orbital transformation (OT) for robustness, followed by tighter convergence passes.
- AIMD protocol: NVT melt at 1500-2000 K (few ps), quench to 300-600 K (several ps), anneal at 300 K. Use CSVR (Bussi) thermostat.
- Restart hygiene: enable PROJECT-1.restart, PROJECT-RESTART.wfn, positions, velocities; keep MOTION/PRINT lean for long runs.
- Post-quench validation gates: density, total RDF and partials, homopolar fractions versus seed targets, edge-sharing to corner-sharing ratio, preservation of 3.02 A feature in GeSe2.

## 3. Vibrational Properties
1. **VDOS from AIMD**
   - Compute velocity autocorrelation (VACF) spectra from equilibrated 300 K trajectories using TRAVIS (time reversibility check, sampling cadence per JCP reference).
   - Track boson-peak evolution across r_mean to verify intermediate-phase behavior noted by Boolchand and Georgiev.
2. **IR absorption from AIMD**
   - Extract dipole moment time series via Wannier centers in CP2K; process with TRAVIS to obtain alpha_vib(omega) up to mid-IR.
   - Flag impurity signatures (e.g., 780 and 1260 cm-1 bands from Ge-O or hydroxyl contamination) and exclude them from KK stitching.

## 4. Electronic Structure Characterization
- Run HSE06 single-point calculations with ADMM on relaxed snapshots to obtain DOS and optical band edges.
- For smaller cells (<= 128 atoms), execute G0W0 in CP2K to calibrate HSE06 gaps; derive scissor corrections where needed.
- Perform Tauc fits and extract Urbach energy, especially along Se60Ge40-xAsx; benchmark against the reported anomaly near x = 5 (Se60Ge35As5).
- Produce projected DOS highlighting Ge, As, Se s/p contributions and document trend versus r_mean.

## 5. Electronic Absorption and epsilon2(omega)
- Assemble vibrational absorption alpha_vib(omega) from Section 3 for frequencies below the electronic gap.
- For the electronic part, combine matrix-element weighted independent-particle transitions at the HSE06 level; where full epsilon2 is impractical, use joint DOS with momentum weighting and GW-calibrated scissor shifts.
- Construct near-edge absorption curves consistent with measured Tauc slopes and Urbach tails along the ternary line.

## 6. Kramers-Kronig (KK) Integration to n(omega)
- Merge vibrational and electronic absorption into a unified alpha(omega) grid from THz through UV.
- Apply KK integration (Python implementation under version control) to recover n(omega) and k(omega), enforcing correct low- and high-frequency extrapolations and sum-rule consistency.
- Cross-check n(0) against static dielectric constants from HSE06 (or GW) and any available low-frequency measurements.

## 7. Validation and Quality Gates
- **Topology:** Ensure homopolar fraction trends versus r_mean and soft-mode fractions follow Mauro-style expectations; confirm ring statistics and motif counts.
- **Rigidity window physics:** Demonstrate best-connected behavior near r_mean 2.3-2.4, aligning with Mauro, Boolchand, and intermediate-phase literature.
- **Vibrational spectra:** Compare VDOS and IR band positions against literature for As2Se3 and GeSe2 anchors.
- **Electronic properties:** Validate HSE06 (plus GW where available) band gaps against experimental references; report Tauc/Urbach evolution per composition.
- **Optical dispersion:** Check that n(omega) curves are smooth and consistent across compositions; reconcile with any provided experimental data.

## 8. Execution on Rescale
- Primary executable: cp2k.psmp with hybrid MPI/OpenMP setup.
- Stage layout: (1) seed melt-quench (classical or short DFT) (2) DFT relax plus 300 K AIMD (3) HSE06 single-points (4) optional GW lanes (5) TRAVIS post-processing (6) KK analysis scripts.
- Configure Rescale job arrays for composition and quench-rate sweeps; capture restarts and outputs per stage for reliable resume behavior.
- Trim CP2K MOTION/PRINT for long AIMD to control I/O; persist wavefunctions and velocities at reasonable cadence for restarts.

## 9. Concrete Deliverables
1. CP2K v9.1 input decks for melt-quench, relax, AIMD, HSE06, and optional GW mini-cells.
2. Reports comparing seeds versus DFT structures: RDF/S(Q), partial RDFs, homopolar fractions, ring and edge-sharing statistics, trend plots versus r_mean.
3. VDOS and IR spectra (TRAVIS), including low-frequency analysis and boson-peak commentary.
4. Electronic DOS, projected DOS, band-edge summaries (HSE06 plus GW calibrations) with Tauc and Urbach fits.
5. epsilon2(omega), n(omega), k(omega) data sets plus KK Python notebooks and raw arrays.
6. Methods note covering Mauro-style seeding rationale, rigidity-window focus, convergence settings, and uncertainty estimates.

## 10. Nice-to-Haves and Future-Proofing
- Composition-matched experimental RDF/S(Q) and densities to tighten acceptance windows and guide RMC refinement.
- At least one high-quality optical data set (IR, Raman, or n(lambda)) for As2Se3, GeSe4, or Se60Ge35As5 to benchmark spectra and KK stitching.
- Progressive adoption of an ML potential trained on in-house DFT data to scale to larger cells and longer trajectories, guided by recent glass simulation reviews.

## Risks and Mitigations
- **Optical workload cost:** Full BSE on large amorphous cells is prohibitive; mitigate by using HSE06 for edges, GW spot checks for calibration, and independent-particle absorption for near-edge slopes.
- **Finite-size and quench artifacts:** Employ >= 240 atom cells, explore multiple seeds, and gate structures against experimental RDF and IR signatures before committing to optics.
- **Seed potential bias:** Validate homopolar fractions, angle distributions, and ring statistics against Mauro and experimental references; re-anneal with DFT when needed.

## Implementation Checklist
- **We will prepare:** CP2K melt-quench and HSE06 input packs, TRAVIS post-processing scripts, Python KK notebook, and Rescale job templates with restart hygiene baked in.
- **Helpful from you:** Composition-matched RDF/S(Q) and density data, plus at least one vetted optical measurement (IR, Raman, or n(lambda)) to pin quench parameters and validate epsilon2 and n(omega).

## Change Log (relative to prior draft)
- Added GeSe4 anchor at r_mean = 2.4 and ternary Se60Ge40-xAsx sweep with x ~ 5 focus.
- Elevated objective gates for seeds: homopolar fraction and soft-mode trends directly from Mauro's work.
- Highlighted impurity-band tracking in IR workflow to avoid contaminating KK analysis.
- Clarified Rescale staging and artifact management for restartable runs.
