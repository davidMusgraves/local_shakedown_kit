#!/usr/bin/env python3
"""Live CP2K MD metrics monitor with NumPy + Matplotlib plots."""

from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional

import matplotlib.pyplot as plt
import numpy as np


MD_LINE = re.compile(r"^\s*MD\|")
FLOAT_RE = re.compile(r"[-+]?\d*\.\d+(?:[EeDd][-+]?\d+)?|[-+]?\d+(?:\.\d+)?(?:[EeDd][-+]?\d+)?")


def parse_float_values(line: str) -> List[float]:
    values = [float(token.replace("D", "E")) for token in FLOAT_RE.findall(line)]
    return values


def finalize_record(record: Dict[str, float]) -> Dict[str, float]:
    pot = record.get("potential_inst")
    kin = record.get("kinetic_inst")
    if record.get("total_energy") is None and pot is not None and kin is not None:
        record["total_energy"] = pot + kin
    pot_avg = record.get("potential_avg")
    kin_avg = record.get("kinetic_avg")
    if record.get("total_energy_avg") is None and pot_avg is not None and kin_avg is not None:
        record["total_energy_avg"] = pot_avg + kin_avg
    return dict(record)


def md_block_stream(path: Path, follow: bool = True) -> Generator[Dict[str, float], None, None]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        current: Optional[Dict[str, float]] = None
        inside_md = False
        while True:
            line = handle.readline()
            if not line:
                if not follow:
                    if current:
                        yield finalize_record(current)
                    break
                time.sleep(0.25)
                continue

            stripped = line.rstrip("\n")
            lower = stripped.lower()

            if MD_LINE.match(stripped):
                if "step number" in lower:
                    if current:
                        yield finalize_record(current)
                    parts = stripped.split()
                    current = {"step": float(parts[-1])}
                    inside_md = True
                elif inside_md and current is not None:
                    values = parse_float_values(stripped)
                    if "time [fs]" in lower and values:
                        current["time_fs"] = values[0]
                    elif "conserved quantity" in lower and values:
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
                    elif "temperature_inst" in lower and values:
                        current["temperature_inst"] = values[0]
                        if len(values) > 1:
                            current["temperature_avg"] = values[1]
                if "md| ***" in lower:
                    inside_md = False
                continue

            if current is None:
                continue

            values = parse_float_values(stripped)
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
                yield finalize_record(current)
                current = None
            elif "energy|" in lower and "total force_eval" in lower and values:
                current["total_energy"] = values[-1]
                yield finalize_record(current)
                current = None


def setup_figure() -> Dict[str, object]:
    plt.ion()
    fig, axes = plt.subplots(4, 1, figsize=(10, 12), sharex=True)
    fig.suptitle("CP2K MD Live Monitor")

    ax_energy, ax_temp, ax_cpu, ax_post = axes
    ax_energy.set_ylabel("Energy [Ha]")
    ax_temp.set_ylabel("Temperature [K]")
    ax_cpu.set_ylabel("CPU / Drift")
    ax_post.set_ylabel("Post-SCF [Ha]")
    ax_post.set_xlabel("MD Step")

    lines = {
        "potential_inst": ax_energy.plot([], [], label="Potential (inst)")[0],
        "kinetic_inst": ax_energy.plot([], [], label="Kinetic (inst)")[0],
        "total": ax_energy.plot([], [], label="Total (inst)")[0],
        "temperature_inst": ax_temp.plot([], [], label="Temperature (inst)", color="tab:red")[0],
        "temperature_avg": ax_temp.plot([], [], label="Temperature (avg)", linestyle="--", color="tab:pink")[0],
        "cpu_time_per_step": ax_cpu.plot([], [], label="CPU time / step [s]")[0],
        "energy_drift_inst": ax_cpu.plot([], [], label="Energy drift / atom [K]", color="tab:green")[0],
        "overlap_energy_core": ax_post.plot([], [], label="Overlap core")[0],
        "self_energy_core": ax_post.plot([], [], label="Self core")[0],
        "core_hamiltonian_energy": ax_post.plot([], [], label="Core Hamiltonian")[0],
        "hartree_energy": ax_post.plot([], [], label="Hartree")[0],
        "exchange_correlation_energy": ax_post.plot([], [], label="Exchange-Correlation")[0],
        "dispersion_energy": ax_post.plot([], [], label="Dispersion")[0],
    }

    for ax in axes:
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="upper right")

    table_ax = fig.add_axes([0.1, 0.02, 0.8, 0.18])
    table_ax.axis("off")

    return {"fig": fig, "axes": axes, "lines": lines, "table_ax": table_ax}


def update_plots(figure_ctx: Dict[str, object], data: Dict[str, List[float]]) -> None:
    lines = figure_ctx["lines"]
    table_ax = figure_ctx["table_ax"]
    fig = figure_ctx["fig"]

    steps = np.array(data["step"]) if data["step"] else np.array([])
    if steps.size == 0:
        return

    lines["potential_inst"].set_data(steps, np.array(data["potential_inst"]))
    lines["kinetic_inst"].set_data(steps, np.array(data["kinetic_inst"]))
    lines["total"].set_data(steps, np.array(data["total_energy"]))
    lines["temperature_inst"].set_data(steps, np.array(data["temperature_inst"]))
    if data["temperature_avg"]:
        lines["temperature_avg"].set_data(steps, np.array(data["temperature_avg"]))
    lines["cpu_time_per_step"].set_data(steps, np.array(data["cpu_time_per_step"]))
    lines["energy_drift_inst"].set_data(steps, np.array(data["energy_drift_inst"]))
    lines["overlap_energy_core"].set_data(steps, np.array(data["overlap_energy_core"]))
    lines["self_energy_core"].set_data(steps, np.array(data["self_energy_core"]))
    lines["core_hamiltonian_energy"].set_data(steps, np.array(data["core_hamiltonian_energy"]))
    lines["hartree_energy"].set_data(steps, np.array(data["hartree_energy"]))
    lines["exchange_correlation_energy"].set_data(steps, np.array(data["exchange_correlation_energy"]))
    lines["dispersion_energy"].set_data(steps, np.array(data["dispersion_energy"]))

    for ax in figure_ctx["axes"]:
        ax.relim()
        ax.autoscale_view()

    table_ax.clear()
    table_ax.axis("off")
    tail = min(5, len(data["step"]))
    indices = range(len(data["step"]) - tail, len(data["step"]))
    headers = [
        "Step",
        "Time [fs]",
        "Temp [K]",
        "Temp avg [K]",
        "Potential [Ha]",
        "Kinetic [Ha]",
        "Total [Ha]",
        "CPU [s]",
        "Drift [K]",
        "Overlap [Ha]",
        "Self [Ha]",
        "Core H [Ha]",
        "Hartree [Ha]",
        "XC [Ha]",
        "Dispersion [Ha]",
    ]
    rows = []
    for idx in indices:
        rows.append(
            [
                int(data["step"][idx]),
                f"{data['time_fs'][idx]:.3f}",
                f"{data['temperature_inst'][idx]:.2f}",
                f"{data['temperature_avg'][idx]:.2f}" if data["temperature_avg"] else "-",
                f"{data['potential_inst'][idx]:.6f}",
                f"{data['kinetic_inst'][idx]:.6f}",
                f"{data['total_energy'][idx]:.6f}",
                f"{data['cpu_time_per_step'][idx]:.3f}",
                f"{data['energy_drift_inst'][idx]:.3f}",
                f"{data['overlap_energy_core'][idx]:.6f}",
                f"{data['self_energy_core'][idx]:.6f}",
                f"{data['core_hamiltonian_energy'][idx]:.6f}",
                f"{data['hartree_energy'][idx]:.6f}",
                f"{data['exchange_correlation_energy'][idx]:.6f}",
                f"{data['dispersion_energy'][idx]:.6f}",
            ]
        )
    table_ax.table(cellText=rows, colLabels=headers, loc="center")

    fig.canvas.draw()
    fig.canvas.flush_events()


def init_data_store() -> Dict[str, List[float]]:
    keys = [
        "step",
        "time_fs",
        "conserved_energy",
        "cpu_time_per_step",
        "cpu_time_per_step_avg",
        "energy_drift_inst",
        "energy_drift_avg",
        "potential_inst",
        "potential_avg",
        "kinetic_inst",
        "kinetic_avg",
        "temperature_inst",
        "temperature_avg",
        "total_energy",
        "total_energy_avg",
        "overlap_energy_core",
        "self_energy_core",
        "core_hamiltonian_energy",
        "hartree_energy",
        "exchange_correlation_energy",
        "dispersion_energy",
    ]
    return {key: [] for key in keys}


def append_record(store: Dict[str, List[float]], record: Dict[str, float]) -> None:
    step = record.get("step")
    if step is None:
        return
    store["step"].append(step)
    for key in store:
        if key == "step":
            continue
        value = record.get(key, np.nan)
        store[key].append(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live plot CP2K MD block metrics")
    parser.add_argument("logfile", help="Path to CP2K output (e.g., md_smoke_compat.out)")
    parser.add_argument(
        "--read-once",
        action="store_true",
        help="Parse existing blocks and exit instead of following for new data",
    )
    args = parser.parse_args()

    log_path = Path(args.logfile)
    if not log_path.exists():
        raise SystemExit(f"Log file not found: {log_path}")

    data_store = init_data_store()
    figure_ctx = setup_figure()

    follow = not args.read_once
    mode = "following" if follow else "reading"
    print(f"Monitoring {log_path} ({mode})")
    for record in md_block_stream(log_path, follow=follow):
        append_record(data_store, record)
        update_plots(figure_ctx, data_store)
        step = int(record["step"])
        temp = record.get("temperature_inst", float("nan"))
        cpu = record.get("cpu_time_per_step", float("nan"))
        pot = record.get("potential_inst", float("nan"))
        kin = record.get("kinetic_inst", float("nan"))
        total = record.get("total_energy", float("nan"))
        hartree = record.get("hartree_energy", float("nan"))
        xc = record.get("exchange_correlation_energy", float("nan"))
        disp = record.get("dispersion_energy", float("nan"))
        print(
            f"Step {step:4d} | T={temp:8.2f} K | CPU={cpu:7.2f} s | Pot={pot:10.4f} Ha | Kin={kin:10.4f} Ha | Tot={total:10.4f} Ha | Hartree={hartree:10.4f} Ha | XC={xc:10.4f} Ha | Disp={disp:10.4f} Ha"
        )

    if not follow:
        print("Reached end of file. Close the plot window to exit.")


if __name__ == "__main__":
    main()
