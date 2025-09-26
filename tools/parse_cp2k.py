#!/usr/bin/env python3
import re, json

def parse_log(logfile):
    """Parse CP2K log file and extract key metrics"""
    if not logfile:
        return {"energies": [], "temperatures": [], "scf_cycles": [], 
                "temperature_mean": None, "temperature_std": None, "scf_cycles_mean": None}
    
    try:
        with open(logfile, 'r') as f:
            content = f.read()
    except:
        return {"energies": [], "temperatures": [], "scf_cycles": [], 
                "temperature_mean": None, "temperature_std": None, "scf_cycles_mean": None}
    
    # Extract energies - multiple patterns
    energies = []
    energy_patterns = [
        r'Total energy:\s+(-?\d+\.\d+)',
        r'Total FORCE_EVAL \( QS \) energy =\s+(-?\d+\.\d+)',
        r'ENERGY\| Total FORCE_EVAL \( QS \) energy =\s+(-?\d+\.\d+)'
    ]
    for pattern in energy_patterns:
        for match in re.finditer(pattern, content):
            energies.append(float(match.group(1)))
    
    # Extract temperatures - multiple patterns
    temperatures = []
    temp_patterns = [
        r'TEMPERATURE\s+(\d+\.\d+)',
        r'TEMPERATURE\s+\[K\]\s+(\d+\.\d+)',
        r'Temperature:\s+(\d+\.\d+)',
        r'T\s+=\s+(\d+\.\d+)'
    ]
    for pattern in temp_patterns:
        for match in re.finditer(pattern, content):
            temperatures.append(float(match.group(1)))
    
    # Extract SCF cycles - multiple patterns
    scf_cycles = []
    scf_patterns = [
        r'Step\s+(\d+)\s+.*?Convergence',
        r'SCF\s+(\d+)\s+.*?Convergence',
        r'Iteration\s+(\d+)\s+.*?Convergence'
    ]
    for pattern in scf_patterns:
        for match in re.finditer(pattern, content):
            scf_cycles.append(int(match.group(1)))
    
    # Calculate statistics
    temp_mean = sum(temperatures) / len(temperatures) if temperatures else None
    temp_std = (sum((t - temp_mean)**2 for t in temperatures) / len(temperatures))**0.5 if temperatures and len(temperatures) > 1 else None
    scf_mean = sum(scf_cycles) / len(scf_cycles) if scf_cycles else None
    
    return {
        "energies": energies,
        "temperatures": temperatures,
        "scf_cycles": scf_cycles,
        "temperature_mean": temp_mean,
        "temperature_std": temp_std,
        "scf_cycles_mean": scf_mean
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = parse_log(sys.argv[1])
        print(json.dumps(result, indent=2))
