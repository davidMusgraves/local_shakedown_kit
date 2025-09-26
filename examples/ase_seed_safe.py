#!/usr/bin/env python3
"""
Quick periodic As-Se seed generator with minimum interatomic distance
to avoid close-contact blowups when scaling to ~60-100 atoms.
"""
import numpy as np
from ase import Atoms
from ase.build import bulk
from ase.visualize import view
import argparse

def generate_as_se_seed(n_atoms=60, min_distance=2.0):
    """
    Generate a safe As-Se seed structure with minimum interatomic distance.
    
    Parameters:
    -----------
    n_atoms : int
        Target number of atoms (default: 60)
    min_distance : float
        Minimum interatomic distance in Angstroms (default: 2.0)
    
    Returns:
    --------
    atoms : ase.Atoms
        Generated structure
    """
    # Calculate approximate composition (roughly 40% As, 60% Se)
    n_as = int(n_atoms * 0.4)
    n_se = n_atoms - n_as
    
    # Create a simple cubic structure
    # Start with a reasonable cell size
    cell_size = (n_atoms * 8.0)**(1/3)  # Rough estimate for density
    
    # Generate random positions
    np.random.seed(42)  # For reproducibility
    positions = np.random.uniform(0, cell_size, (n_atoms, 3))
    
    # Create species list
    species = ['As'] * n_as + ['Se'] * n_se
    np.random.shuffle(species)
    
    # Create atoms object
    atoms = Atoms(species, positions=positions, cell=[cell_size, cell_size, cell_size], pbc=True)
    
    # Apply minimum distance constraint
    # Simple approach: if atoms are too close, move one randomly
    max_iterations = 1000
    iteration = 0
    
    while iteration < max_iterations:
        distances = atoms.get_all_distances()
        too_close = np.where((distances > 0) & (distances < min_distance))
        
        if len(too_close[0]) == 0:
            break
            
        # Move one of the too-close atoms
        i, j = too_close[0][0], too_close[1][0]
        if i != j:  # Don't move atom to itself
            # Random displacement
            displacement = np.random.uniform(-1, 1, 3)
            atoms.positions[i] += displacement
            # Wrap back into cell
            atoms.positions[i] = atoms.positions[i] % atoms.cell.diagonal()
        
        iteration += 1
    
    if iteration >= max_iterations:
        print(f"Warning: Could not achieve minimum distance {min_distance} Å in {max_iterations} iterations")
    
    return atoms

def main():
    parser = argparse.ArgumentParser(description='Generate safe As-Se seed structure')
    parser.add_argument('--n_atoms', type=int, default=60, help='Number of atoms (default: 60)')
    parser.add_argument('--min_distance', type=float, default=2.0, help='Minimum interatomic distance (default: 2.0)')
    parser.add_argument('--output', type=str, default='as_se_seed.xyz', help='Output filename (default: as_se_seed.xyz)')
    parser.add_argument('--view', action='store_true', help='View structure with ASE GUI')
    
    args = parser.parse_args()
    
    print(f"Generating As-Se seed with {args.n_atoms} atoms...")
    print(f"Minimum interatomic distance: {args.min_distance} Å")
    
    atoms = generate_as_se_seed(args.n_atoms, args.min_distance)
    
    # Write to file
    atoms.write(args.output)
    print(f"Structure written to {args.output}")
    
    # Print some statistics
    distances = atoms.get_all_distances()
    min_dist = np.min(distances[distances > 0])
    print(f"Actual minimum distance: {min_dist:.3f} Å")
    print(f"Cell size: {atoms.cell.diagonal()}")
    print(f"Composition: {dict(zip(*np.unique(atoms.get_chemical_symbols(), return_counts=True)))}")
    
    if args.view:
        view(atoms)

if __name__ == "__main__":
    main()