#!/usr/bin/env python3
"""Render the CP2K Streamlit dashboard for an existing log file."""

from __future__ import annotations

import argparse
import json
import os
import socket
import shutil
import subprocess
import tempfile
import webbrowser
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

MD_PREFIX = "MD|"


def parse_float(token: str) -> float:
    token = token.replace("D", "E")
    return float(token)


def parse_log(path: Path) -> Dict[str, List[float]]:
    store = {
        "step": [],
        "time_fs": [],
        "conserved_energy": [],
        "cpu_time_per_step": [],
        "cpu_time_per_step_avg": [],
        "energy_drift_inst": [],
        "energy_drift_avg": [],
        "potential_inst": [],
        "potential_avg": [],
        "kinetic_inst": [],
        "kinetic_avg": [],
        "temperature_inst": [],
        "temperature_avg": [],
        "total_energy": [],
        "total_energy_avg": [],
        "overlap_energy_core": [],
        "self_energy_core": [],
        "core_hamiltonian_energy": [],
        "hartree_energy": [],
        "exchange_correlation_energy": [],
        "dispersion_energy": [],
    }
    blocks: List[Dict[str, float]] = []
    current: Optional[Dict[str, float]] = None
    inside_md = False

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            stripped = line.lstrip()
            lower = stripped.lower()

            if stripped.startswith(MD_PREFIX):
                if "step number" in stripped:
                    if current:
                        finalize_block(current, store, blocks)
                    parts = line.split()
                    current = {"step": float(parts[-1])}
                    inside_md = True
                elif inside_md and current:
                    values = [parse_float(tok) for tok in stripped.split() if _is_number(tok)]
                    if "time [fs]" in stripped and values:
                        current["time_fs"] = values[0]
                    elif "conserved quantity" in stripped and values:
                        current["conserved_energy"] = values[0]
                    elif "cpu time per md step" in lower and values:
                        current["cpu_time_per_step"] = values[0]
                        if len(values) > 1:
                            current["cpu_time_per_step_avg"] = values[1]
                    elif "energy drift per atom" in lower and values:
                        current["energy_drift_inst"] = values[0]
                        if len(values) > 1:
                            current["energy_drift_avg"] = values[1]
                    elif "potential energy" in lower and values:
                        current["potential_inst"] = values[0]
                        if len(values) > 1:
                            current["potential_avg"] = values[1]
                    elif "kinetic energy" in lower and values:
                        current["kinetic_inst"] = values[0]
                        if len(values) > 1:
                            current["kinetic_avg"] = values[1]
                    elif "temperature" in lower and values:
                        current["temperature_inst"] = values[0]
                        if len(values) > 1:
                            current["temperature_avg"] = values[1]
                if "md| ***" in lower:
                    inside_md = False
                continue

            if current is None:
                continue

            values = [parse_float(tok) for tok in stripped.split() if _is_number(tok)]
            if "overlap energy of the core charge distribution" in lower and values:
                current["overlap_energy_core"] = values[0]
            elif "self energy of the core charge distribution" in lower and values:
                current["self_energy_core"] = values[0]
            elif "core hamiltonian energy" in lower and values:
                current["core_hamiltonian_energy"] = values[0]
            elif "hartree energy" in lower and values:
                current["hartree_energy"] = values[0]
            elif "exchange-correlation energy" in lower and values:
                current["exchange_correlation_energy"] = values[0]
            elif "dispersion energy" in lower and values:
                current["dispersion_energy"] = values[0]
            elif "total energy:" in lower and values:
                current["total_energy"] = values[0]
                finalize_block(current, store, blocks)
                current = None
            elif "total force_eval" in lower and values:
                current["total_energy"] = values[-1]
                finalize_block(current, store, blocks)
                current = None

    if current:
        finalize_block(current, store, blocks)
    store["blocks"] = blocks
    return store



def finalize_block(block: Dict[str, float], store: Dict[str, List[float]], blocks: List[Dict[str, float]]) -> None:
    if "step" not in block:
        return
    pot = block.get("potential_inst")
    kin = block.get("kinetic_inst")
    if pot is not None and kin is not None:
        block.setdefault("total_energy", pot + kin)
    pot_avg = block.get("potential_avg")
    kin_avg = block.get("kinetic_avg")
    if pot_avg is not None and kin_avg is not None:
        block.setdefault("total_energy_avg", pot_avg + kin_avg)
    blocks.append(dict(block))
    for key in store:
        if key == "blocks":
            continue
        value = block.get(key)
        if value is not None:
            store[key].append(value)
        else:
            store[key].append(float("nan"))


def _is_number(token: str) -> bool:
    try:
        parse_float(token)
        return True
    except ValueError:
        return False


def tail_lines(path: Path, max_lines: int = 100) -> List[str]:
    dq: deque[str] = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            dq.append(line.rstrip("\n"))
    return list(dq)


def pretty_input(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    rendered: List[str] = []
    indent = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                stripped = raw.strip()
                if not stripped or stripped.startswith("!"):
                    continue
                upper = stripped.upper()
                if upper.startswith("&END"):
                    indent = max(indent - 1, 0)
                rendered.append("  " * indent + stripped)
                if upper.startswith("&") and not upper.startswith("&END"):
                    indent += 1
                if len(rendered) >= 200:
                    rendered.append("... <truncated>")
                    break
    except OSError:
        return ""
    return "\n".join(rendered)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def build_state(log_path: Path, store: Dict[str, List[float]], project: str, input_path: Optional[Path]) -> Dict[str, object]:
    blocks = store.pop("blocks")
    status = "completed"
    return {
        "project": project,
        "logfile": str(log_path),
        "input_path": str(input_path) if input_path else None,
        "profile": "offline",
        "mode": "MD",
        "status": status,
        "runtime": 0.0,
        "return_code": 0,
        "pid": None,
        "tail": tail_lines(log_path, 100),
        "metrics": {key: store[key] for key in store},
        "blocks": blocks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch Streamlit dashboard for a finished CP2K run")
    parser.add_argument("logfile", help="CP2K output file (e.g., md_loose_smear.out)")
    parser.add_argument("--input", help="Associated CP2K input file")
    parser.add_argument("--project", help="Project name for display")
    args = parser.parse_args()

    log_path = Path(args.logfile)
    if not log_path.exists():
        raise SystemExit(f"Log file not found: {log_path}")

    store = parse_log(log_path)
    if not store["step"]:
        raise SystemExit("No MD blocks found in log")

    project = args.project or log_path.stem
    input_path = Path(args.input) if args.input else None
    state = build_state(log_path, store, project, input_path)

    streamlit_exec = shutil.which("streamlit")
    if not streamlit_exec:
        raise SystemExit("streamlit executable not found in PATH")

    with tempfile.TemporaryDirectory(prefix="cp2k_dash_offline_") as tmpdir:
        state_path = Path(tmpdir) / "state.json"
        state_path.write_text(json.dumps(state, indent=2))
        env = os.environ.copy()
        env.update(
            {
                "CP2K_DASHBOARD_STATE": str(state_path),
                "CP2K_DASHBOARD_PROJECT": project,
                "CP2K_DASHBOARD_MODE": "MD",
                "CP2K_DASHBOARD_PROFILE": "offline",
                "CP2K_DASHBOARD_LOGFILE": str(log_path),
                "CP2K_DASHBOARD_INPUT": pretty_input(input_path),
                "CP2K_DASHBOARD_REFRESH_MS": "1000000",
            }
        )
        app_path = Path(__file__).resolve().parent / "streamlit_dashboard.py"
        port = find_free_port()
        url = f"http://localhost:{port}"
        print(f"Streamlit dashboard available at {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        cmd = [streamlit_exec, "run", str(app_path), "--server.port", str(port)]
        subprocess.run(cmd, env=env, check=False)


if __name__ == "__main__":
    main()
