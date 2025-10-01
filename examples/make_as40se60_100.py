#!/usr/bin/env python3
"""Generate a 100-atom As40Se60 random seed structure for melt-quench tests."""

from __future__ import annotations

import math
import random
from pathlib import Path

# Target composition
N_AS = 40
N_SE = 60
N_TOTAL = N_AS + N_SE

# Physical constants
M_AS = 74.921595  # g/mol
M_SE = 78.971     # g/mol
AVOGADRO = 6.02214076e23
TARGET_DENSITY = 4.6  # g/cm^3 (approximate bulk density of As2Se3)

# Output path
OUTPUT = Path("inputs/as40se60_100_seed.xyz")


def compute_cell_length() -> float:
    mass_g = (N_AS * M_AS + N_SE * M_SE) / AVOGADRO  # grams
    volume_cm3 = mass_g / TARGET_DENSITY
    volume_ang3 = volume_cm3 * 1.0e24
    cell_length = volume_ang3 ** (1.0 / 3.0)
    return cell_length


def random_position(cell: float) -> tuple[float, float, float]:
    return (random.random() * cell, random.random() * cell, random.random() * cell)


def minimum_distance(a: tuple[float, float, float], b: tuple[float, float, float], cell: float) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    dz = abs(a[2] - b[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def generate_positions(cell: float, min_sep: float = 2.1) -> list[tuple[str, tuple[float, float, float]]]:
    species = ["As"] * N_AS + ["Se"] * N_SE
    random.shuffle(species)
    positions: list[tuple[str, tuple[float, float, float]]] = []
    attempts = 0
    for element in species:
        while True:
            pos = random_position(cell)
            if all(minimum_distance(pos, p, cell) >= min_sep for _, p in positions):
                positions.append((element, pos))
                break
            attempts += 1
            if attempts > 50000:
                raise RuntimeError("Failed to place atoms with the requested minimum separation")
    return positions


def write_xyz(cell: float, positions: list[tuple[str, tuple[float, float, float]]]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as handle:
        handle.write(f"{N_TOTAL}\n")
        handle.write(f"As40Se60 seed cell={cell:.4f} Angstrom (density ~{TARGET_DENSITY} g/cm^3)\n")
        for element, (x, y, z) in positions:
            handle.write(f"{element:2s} {x:12.6f} {y:12.6f} {z:12.6f}\n")


def main() -> None:
    random.seed(2025)
    cell = compute_cell_length()
    positions = generate_positions(cell)
    write_xyz(cell, positions)
    print(f"Wrote {OUTPUT} with cell length {cell:.4f} Ang")


if __name__ == "__main__":
    main()
