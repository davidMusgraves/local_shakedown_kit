#!/usr/bin/env python3
"""Run CP2K and surface an interactive dashboard while the job is active."""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


def which(candidate: str) -> Optional[str]:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        path = os.path.join(directory, candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def default_inp(mode: Optional[str], profile: Optional[str]) -> Optional[str]:
    if not mode:
        return None
    effective = profile or "compat"
    return f"inputs/{mode}_smoke_{effective}.inp"


def _isatty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM", "dumb") != "dumb"


def pretty_cp2k_input(path: str, max_lines: int = 120) -> List[str]:
    """Return an indented, comment-free rendering of a CP2K input file."""

    if not path or not os.path.exists(path):
        return ["<input file not found>"]

    rendered: List[str] = []
    indent = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("!"):
                    continue
                upper = stripped.upper()
                if upper.startswith("&END"):
                    indent = max(indent - 1, 0)
                rendered.append("  " * indent + stripped)
                if upper.startswith("&") and not upper.startswith("&END"):
                    indent += 1
                if len(rendered) >= max_lines:
                    rendered.append("... <truncated>")
                    break
    except OSError as exc:  # pragma: no cover - best effort formatting
        rendered = [f"<failed to read input: {exc}>"]
    if not rendered:
        rendered = ["<empty input file>"]
    return rendered


ASCII_BARS = " .:-=+*#%@"


def sparkline(values: List[float], width: int) -> str:
    if not values or width <= 0:
        return ""
    if len(values) <= width:
        sample = values
    else:
        step = len(values) / float(width)
        sample = [values[int(i * step)] for i in range(width)]
    vmin = min(sample)
    vmax = max(sample)
    if math.isclose(vmin, vmax):
        return ASCII_BARS[-1] * len(sample)
    span = vmax - vmin
    scale = len(ASCII_BARS) - 1
    return "".join(ASCII_BARS[int((value - vmin) / span * scale)] for value in sample)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


@dataclass
class MetricSeries:
    steps: List[Optional[int]] = field(default_factory=list)
    time_fs: List[Optional[float]] = field(default_factory=list)
    conserved_energy: List[Optional[float]] = field(default_factory=list)
    cpu_time_per_step: List[Optional[float]] = field(default_factory=list)
    cpu_time_per_step_avg: List[Optional[float]] = field(default_factory=list)
    energy_drift_inst: List[Optional[float]] = field(default_factory=list)
    energy_drift_avg: List[Optional[float]] = field(default_factory=list)
    potential_inst: List[Optional[float]] = field(default_factory=list)
    potential_avg: List[Optional[float]] = field(default_factory=list)
    kinetic_inst: List[Optional[float]] = field(default_factory=list)
    kinetic_avg: List[Optional[float]] = field(default_factory=list)
    temperature_inst: List[Optional[float]] = field(default_factory=list)
    temperature_avg: List[Optional[float]] = field(default_factory=list)
    total_energy: List[Optional[float]] = field(default_factory=list)
    total_energy_avg: List[Optional[float]] = field(default_factory=list)

    def add_block(self, block: Dict[str, Optional[float]]) -> None:
        self.steps.append(block.get("step"))
        self.time_fs.append(block.get("time_fs"))
        self.conserved_energy.append(block.get("conserved_energy"))
        self.cpu_time_per_step.append(block.get("cpu_time_per_step"))
        self.cpu_time_per_step_avg.append(block.get("cpu_time_per_step_avg"))
        self.energy_drift_inst.append(block.get("energy_drift_inst"))
        self.energy_drift_avg.append(block.get("energy_drift_avg"))
        self.potential_inst.append(block.get("potential_inst"))
        self.potential_avg.append(block.get("potential_avg"))
        self.kinetic_inst.append(block.get("kinetic_inst"))
        self.kinetic_avg.append(block.get("kinetic_avg"))
        self.temperature_inst.append(block.get("temperature_inst"))
        self.temperature_avg.append(block.get("temperature_avg"))
        self.total_energy.append(block.get("total_energy"))
        self.total_energy_avg.append(block.get("total_energy_avg"))

    def as_blocks(self) -> List[Dict[str, Optional[float]]]:
        result: List[Dict[str, Optional[float]]] = []
        for idx, step in enumerate(self.steps):
            block = {
                "step": step,
                "time_fs": self.time_fs[idx] if idx < len(self.time_fs) else None,
                "conserved_energy": self.conserved_energy[idx] if idx < len(self.conserved_energy) else None,
                "cpu_time_per_step": self.cpu_time_per_step[idx] if idx < len(self.cpu_time_per_step) else None,
                "cpu_time_per_step_avg": self.cpu_time_per_step_avg[idx] if idx < len(self.cpu_time_per_step_avg) else None,
                "energy_drift_inst": self.energy_drift_inst[idx] if idx < len(self.energy_drift_inst) else None,
                "energy_drift_avg": self.energy_drift_avg[idx] if idx < len(self.energy_drift_avg) else None,
                "potential_inst": self.potential_inst[idx] if idx < len(self.potential_inst) else None,
                "potential_avg": self.potential_avg[idx] if idx < len(self.potential_avg) else None,
                "kinetic_inst": self.kinetic_inst[idx] if idx < len(self.kinetic_inst) else None,
                "kinetic_avg": self.kinetic_avg[idx] if idx < len(self.kinetic_avg) else None,
                "temperature_inst": self.temperature_inst[idx] if idx < len(self.temperature_inst) else None,
                "temperature_avg": self.temperature_avg[idx] if idx < len(self.temperature_avg) else None,
                "total_energy": self.total_energy[idx] if idx < len(self.total_energy) else None,
                "total_energy_avg": self.total_energy_avg[idx] if idx < len(self.total_energy_avg) else None,
            }
            result.append(block)
        return result


class RunState:
    def __init__(self, project: str, logfile: str, input_path: str, profile: Optional[str], mode: Optional[str]):
        self.project = project
        self.logfile = logfile
        self.input_path = input_path
        self.profile = profile
        self.mode = mode
        self.tail: Deque[str] = deque(maxlen=100)
        self.metrics = MetricSeries()
        self.blocks: List[Dict[str, Optional[float]]] = []
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.status = "launching"
        self.return_code: Optional[int] = None
        self.pid: Optional[int] = None
        self.done = threading.Event()
        self.cancel_requested = False
        self._last_step: Optional[int] = None
        self._current_block: Optional[Dict[str, Optional[float]]] = None
        self._state_file: Optional[pathlib.Path] = None
        self._last_snapshot_write: float = 0.0
        self.echo_to_stdout: bool = False

    def runtime(self) -> float:
        return time.time() - self.start_time

    def snapshot(self) -> Dict[str, object]:
        with self.lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> Dict[str, object]:
        return {
            "project": self.project,
            "logfile": self.logfile,
            "input_path": self.input_path,
            "profile": self.profile,
            "mode": self.mode,
            "status": self.status,
            "runtime": self.runtime(),
            "return_code": self.return_code,
            "pid": self.pid,
            "tail": list(self.tail),
            "metrics": {
                "steps": list(self.metrics.steps),
                "time_fs": list(self.metrics.time_fs),
                "conserved_energy": list(self.metrics.conserved_energy),
                "cpu_time_per_step": list(self.metrics.cpu_time_per_step),
                "cpu_time_per_step_avg": list(self.metrics.cpu_time_per_step_avg),
                "energy_drift_inst": list(self.metrics.energy_drift_inst),
                "energy_drift_avg": list(self.metrics.energy_drift_avg),
                "potential_inst": list(self.metrics.potential_inst),
                "potential_avg": list(self.metrics.potential_avg),
                "kinetic_inst": list(self.metrics.kinetic_inst),
                "kinetic_avg": list(self.metrics.kinetic_avg),
                "temperature_inst": list(self.metrics.temperature_inst),
                "temperature_avg": list(self.metrics.temperature_avg),
                "total_energy": list(self.metrics.total_energy),
                "total_energy_avg": list(self.metrics.total_energy_avg),
            },
            "blocks": [dict(block) for block in self.blocks],
        }

    def append_tail(self, line: str) -> None:
        with self.lock:
            self.tail.append(line.rstrip("\n"))
        self.write_snapshot()

    def set_state_file(self, path: Optional[pathlib.Path]) -> None:
        with self.lock:
            self._state_file = pathlib.Path(path) if path is not None else None

    def write_snapshot(self, force: bool = False) -> None:
        with self.lock:
            if self._state_file is None:
                return
            now = time.time()
            if not force and (now - self._last_snapshot_write) < 0.5:
                return
            snapshot = self._snapshot_locked()
            self._last_snapshot_write = now
            path = self._state_file
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(path.suffix + ".tmp")
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, indent=2)
            os.replace(temp_path, path)
        except OSError:
            pass

    def is_block_open(self) -> bool:
        with self.lock:
            return self._current_block is not None

    def start_block(self) -> None:
        with self.lock:
            self._current_block = {}

    def set_block_values(self, **values: Optional[float]) -> None:
        with self.lock:
            if self._current_block is None:
                self._current_block = {}
            for key, value in values.items():
                if value is not None:
                    self._current_block[key] = value

    def finalize_block(self) -> None:
        block: Optional[Dict[str, Optional[float]]] = None
        with self.lock:
            if not self._current_block or "step" not in self._current_block:
                self._current_block = None
                return
            block = dict(self._current_block)
            potential = block.get("potential_inst")
            kinetic = block.get("kinetic_inst")
            if block.get("total_energy") is None and potential is not None and kinetic is not None:
                block["total_energy"] = potential + kinetic
            potential_avg = block.get("potential_avg")
            kinetic_avg = block.get("kinetic_avg")
            if block.get("total_energy_avg") is None and potential_avg is not None and kinetic_avg is not None:
                block["total_energy_avg"] = potential_avg + kinetic_avg
            self.blocks.append(block)
            self.metrics.add_block(block)
            if block.get("step") is not None:
                self._last_step = int(block["step"])
            self._current_block = None
        self.write_snapshot()

    def _update_metric_value(self, key: str, index: int, value: Optional[float]) -> None:
        if value is None:
            return
        mapping = {
            "time_fs": "time_fs",
            "conserved_energy": "conserved_energy",
            "cpu_time_per_step": "cpu_time_per_step",
            "cpu_time_per_step_avg": "cpu_time_per_step_avg",
            "energy_drift_inst": "energy_drift_inst",
            "energy_drift_avg": "energy_drift_avg",
            "potential_inst": "potential_inst",
            "potential_avg": "potential_avg",
            "kinetic_inst": "kinetic_inst",
            "kinetic_avg": "kinetic_avg",
            "temperature_inst": "temperature_inst",
            "temperature_avg": "temperature_avg",
            "total_energy": "total_energy",
            "total_energy_avg": "total_energy_avg",
        }
        attr = mapping.get(key)
        if not attr:
            return
        series = getattr(self.metrics, attr)
        if index < len(series):
            series[index] = value

    def update_latest_block(self, **values: Optional[float]) -> None:
        should_write = False
        with self.lock:
            if self._current_block is not None:
                for key, value in values.items():
                    if value is not None:
                        self._current_block[key] = value
                        should_write = True
            elif self.blocks:
                block = self.blocks[-1]
                target_index = len(self.blocks) - 1
                for key, value in values.items():
                    if value is not None:
                        block[key] = value
                        self._update_metric_value(key, target_index, value)
                        should_write = True
            else:
                return
        if should_write:
            self.write_snapshot()

    def set_pid(self, pid: int) -> None:
        with self.lock:
            self.pid = pid

    def mark_status(self, status: str) -> None:
        with self.lock:
            self.status = status

    def finalize(self, return_code: int) -> None:
        with self.lock:
            self.return_code = return_code
            self.status = "completed" if return_code == 0 else f"failed ({return_code})"
        self.done.set()
        self.write_snapshot(force=True)

    def request_cancel(self) -> None:
        with self.lock:
            self.cancel_requested = True

    def cancelled(self) -> bool:
        with self.lock:
            return self.cancel_requested


def parse_line_for_metrics(line: str, state: RunState) -> None:
    text = line.rstrip("\n")
    if not text.strip():
        return
    lower = text.lower()

    if text.startswith(" MD|"):
        if text.startswith(" MD| ***"):
            if state.is_block_open():
                state.finalize_block()
            else:
                state.start_block()
            return
        if not state.is_block_open():
            return
        numbers = [_to_float(tok) for tok in text.split() if _is_float(tok)]
        if "step number" in lower:
            value = numbers[-1] if numbers else None
            if value is not None:
                state.set_block_values(step=int(round(value)))
        elif "time [fs]" in lower:
            if numbers:
                state.set_block_values(time_fs=numbers[0])
        elif "conserved quantity" in lower:
            if numbers:
                state.set_block_values(conserved_energy=numbers[0])
        elif "cpu time per md step" in lower:
            first = numbers[0] if numbers else None
            second = numbers[1] if len(numbers) > 1 else None
            state.set_block_values(cpu_time_per_step=first, cpu_time_per_step_avg=second)
        elif "energy drift per atom" in lower:
            first = numbers[0] if numbers else None
            second = numbers[1] if len(numbers) > 1 else None
            state.set_block_values(energy_drift_inst=first, energy_drift_avg=second)
        elif "potential energy" in lower:
            first = numbers[0] if numbers else None
            second = numbers[1] if len(numbers) > 1 else None
            state.set_block_values(potential_inst=first, potential_avg=second)
        elif "kinetic energy" in lower:
            first = numbers[0] if numbers else None
            second = numbers[1] if len(numbers) > 1 else None
            state.set_block_values(kinetic_inst=first, kinetic_avg=second)
        elif "temperature" in lower:
            first = numbers[0] if numbers else None
            second = numbers[1] if len(numbers) > 1 else None
            state.set_block_values(temperature_inst=first, temperature_avg=second)
        state.write_snapshot()
    elif "energy|" in lower and "total force_eval" in lower:
        numbers = [_to_float(tok) for tok in text.split() if _is_float(tok)]
        if numbers:
            state.update_latest_block(total_energy=numbers[-1])


def _is_float(token: str) -> bool:
    try:
        float(token.replace("D", "E"))
        return True
    except ValueError:
        return False


def _to_float(token: str) -> float:
    return float(token.replace("D", "E"))


def run_cp2k_process(cp2k: str, inp: str, env: Dict[str, str], state: RunState) -> int:
    state.mark_status("running")
    with subprocess.Popen(
        [cp2k, "-i", inp],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        bufsize=1,
        universal_newlines=True,
    ) as proc, open(state.logfile, "w", buffering=1, encoding="utf-8", errors="ignore") as log:
        state.set_pid(proc.pid or 0)

        def reader() -> None:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                state.append_tail(raw_line)
                parse_line_for_metrics(raw_line, state)
                log.write(raw_line)
                if state.echo_to_stdout:
                    sys.stdout.write(raw_line)
                    sys.stdout.flush()
            proc.stdout.close()

        reader_thread = threading.Thread(target=reader, name="cp2k-log-reader", daemon=True)
        reader_thread.start()

        while proc.poll() is None:
            if state.cancelled():
                try:
                    proc.send_signal(signal.SIGINT)
                except ProcessLookupError:
                    pass
                break
            time.sleep(0.1)

        reader_thread.join()
        return_code = proc.wait()
    state.finalize(return_code)
    return return_code


def format_seconds(seconds: float) -> str:
    seconds = max(0.0, seconds)
    mins, secs = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs >= 1:
        return f"{int(hrs)}h{int(mins):02d}m{int(secs):02d}s"
    if mins >= 1:
        return f"{int(mins)}m{int(secs):02d}s"
    return f"{secs:.1f}s"


def dashboard_loop(state: RunState, input_render: List[str]) -> None:
    try:
        import curses
    except Exception:
        return

    def _loop(stdscr: "curses._CursesWindow") -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(200)

        def safe_addnstr(row: int, col: int, text: str, max_cols: int) -> None:
            if max_cols <= 0:
                return
            height, width = stdscr.getmaxyx()
            if row < 0 or row >= height:
                return
            try:
                stdscr.addnstr(row, col, text, min(max_cols, width - col))
            except Exception:
                pass

        while True:
            stdscr.erase()
            snap = state.snapshot()
            height, width = stdscr.getmaxyx()

            header_lines = [
                f"Project: {snap['project']}  Mode: {snap.get('mode') or '-'}  Profile: {snap.get('profile') or '-'}",
                f"Status: {snap['status']}  Runtime: {format_seconds(snap['runtime'])}  PID: {snap.get('pid') or '-'}",
                f"Log: {snap['logfile']}  Input: {snap['input_path']}",
                "Keys: q quit dashboard  c cancel run",
            ]
            y = 0
            for line in header_lines:
                safe_addnstr(y, 0, line, width - 1)
                y += 1

            y += 1
            safe_addnstr(y, 0, "Input Summary", width - 1)
            y += 1
            max_input_height = max(4, height // 3)
            for idx in range(min(max_input_height, len(input_render))):
                safe_addnstr(y + idx, 2, input_render[idx], width - 4)
            y += max_input_height + 1

            metrics = snap["metrics"]
            safe_addnstr(y, 0, "Run Metrics", width - 1)
            y += 1
            md_steps = metrics.get("steps", [])
            time_fs = metrics.get("time_fs", [])
            conserved = metrics.get("conserved_energy", [])
            cpu_time = metrics.get("cpu_time_per_step", [])
            cpu_time_avg = metrics.get("cpu_time_per_step_avg", [])
            drift = metrics.get("energy_drift_inst", [])
            drift_avg = metrics.get("energy_drift_avg", [])
            potentials = metrics.get("potential_inst", [])
            potentials_avg = metrics.get("potential_avg", [])
            kinetics = metrics.get("kinetic_inst", [])
            kinetics_avg = metrics.get("kinetic_avg", [])
            temperatures = metrics.get("temperature_inst", [])
            temperatures_avg = metrics.get("temperature_avg", [])
            energies = metrics.get("total_energy", [])
            energies_avg = metrics.get("total_energy_avg", [])
            latest_step = md_steps[-1] if md_steps else None
            latest_time = time_fs[-1] if time_fs else None
            latest_conserved = conserved[-1] if conserved else None
            latest_drift = drift[-1] if drift else None
            latest_temp = temperatures[-1] if temperatures else None
            latest_pot = potentials[-1] if potentials else None
            latest_kin = kinetics[-1] if kinetics else None
            latest_energy = energies[-1] if energies else None
            latest_cpu = cpu_time[-1] if cpu_time else None
            pos_candidate = f"{snap['project']}-pos-1.xyz"
            pos_status = pos_candidate if os.path.exists(pos_candidate) else "(pending write)"
            table_rows = [
                f"MD steps: {len(md_steps)}" + (f" (last {latest_step})" if latest_step is not None else ""),
                f"Time [fs]: {latest_time:.4f}" if latest_time is not None else "Time [fs]: -",
                f"CPU time / step [s]: {latest_cpu:.3f}" if latest_cpu is not None else "CPU time / step [s]: -",
                f"Temperature [K]: {latest_temp:.2f}" if latest_temp is not None else "Temperature [K]: -",
                f"Potential E [Ha]: {latest_pot:.6f}" if latest_pot is not None else "Potential E [Ha]: -",
                f"Kinetic E [Ha]: {latest_kin:.6f}" if latest_kin is not None else "Kinetic E [Ha]: -",
                f"Total E [Ha]: {latest_energy:.6f}" if latest_energy is not None else "Total E [Ha]: -",
                f"Conserved E [Ha]: {latest_conserved:.6f}" if latest_conserved is not None else "Conserved E [Ha]: -",
                f"Energy drift / atom [K]: {latest_drift:.6f}" if latest_drift is not None else "Energy drift / atom [K]: -",
                f"Potential E avg [Ha]: {potentials_avg[-1]:.6f}" if potentials_avg else "Potential E avg [Ha]: -",
                f"Kinetic E avg [Ha]: {kinetics_avg[-1]:.6f}" if kinetics_avg else "Kinetic E avg [Ha]: -",
                f"Total E avg [Ha]: {energies_avg[-1]:.6f}" if energies_avg else "Total E avg [Ha]: -",
                f"Energy drift avg [K]: {drift_avg[-1]:.6f}" if drift_avg else "Energy drift avg [K]: -",
                f"Positions file: {pos_status}",
            ]
            for row in table_rows:
                safe_addnstr(y, 2, row, width - 4)
                y += 1

            chart_width = max(10, width - 4)
            if potentials:
                safe_addnstr(y, 2, f"Potential energy trend: {sparkline(potentials, min(chart_width, 60))}", width - 4)
                y += 1
            if energies:
                safe_addnstr(y, 2, f"Total energy trend:     {sparkline(energies, min(chart_width, 60))}", width - 4)
                y += 1
            if temperatures:
                safe_addnstr(y, 2, f"Temperature trend:    {sparkline(temperatures, min(chart_width, 60))}", width - 4)
                y += 1

            y += 1
            safe_addnstr(y, 0, "Output Tail (last 100 lines)", width - 1)
            y += 1
            available_rows = max(0, height - y - 1)
            tail_lines = snap["tail"][-available_rows:] if available_rows else []
            for idx, line in enumerate(tail_lines):
                safe_addnstr(y + idx, 2, line, width - 4)

            stdscr.refresh()

            ch = stdscr.getch()
            if ch == ord("q"):
                break
            if ch == ord("c"):
                state.request_cancel()

            if state.done.is_set():
                if state.runtime() > 0.5:
                    time.sleep(0.5)
                break

    curses.wrapper(_loop)


def launch_streamlit(state: RunState, input_render: List[str]) -> Optional[Dict[str, object]]:
    streamlit_exec = which("streamlit")
    if not streamlit_exec:
        return None
    dashboard_dir = pathlib.Path(tempfile.mkdtemp(prefix="cp2k_dash_"))
    state_path = dashboard_dir / "state.json"
    state.set_state_file(state_path)
    state.write_snapshot(force=True)

    port = find_free_port()
    app_path = pathlib.Path(__file__).resolve().parent / "streamlit_dashboard.py"
    if not app_path.exists():
        return None

    env = os.environ.copy()
    env.update(
        {
            "CP2K_DASHBOARD_STATE": str(state_path),
            "CP2K_DASHBOARD_PROJECT": state.project,
            "CP2K_DASHBOARD_PROFILE": state.profile or "-",
            "CP2K_DASHBOARD_MODE": state.mode or "-",
            "CP2K_DASHBOARD_INPUT": "\n".join(input_render),
            "CP2K_DASHBOARD_LOGFILE": state.logfile,
            "CP2K_DASHBOARD_REFRESH_MS": os.environ.get("CP2K_DASHBOARD_REFRESH_MS", "1000"),
        }
    )

    cmd = [
        streamlit_exec,
        "run",
        str(app_path),
        "--server.headless",
        "true",
        "--server.port",
        str(port),
    ]
    proc = subprocess.Popen(cmd, env=env)
    print(f"Streamlit dashboard available at http://localhost:{port}")
    return {"process": proc, "dir": dashboard_dir, "state_path": state_path, "port": port}


def basic_run(cp2k: str, inp: str, env: Dict[str, str], logfile: str) -> int:
    with open(logfile, "w", encoding="utf-8", errors="ignore") as fout:
        proc = subprocess.Popen(
            [cp2k, "-i", inp],
            stdout=fout,
            stderr=subprocess.STDOUT,
            env=env,
        )
        return_code = proc.wait()
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CP2K with optional live dashboard.")
    parser.add_argument("inp", nargs="?", help="Explicit input file path")
    parser.add_argument("--mode", choices=["sp", "md"], help="Smoke-test mode")
    parser.add_argument("--profile", choices=["compat", "fast"], default="compat", help="Input profile")
    parser.add_argument("--project", help="Override CP2K PROJECT name")
    parser.add_argument("--cp2k", help="Path to cp2k executable (cp2k.psmp or cp2k)")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable the interactive dashboard")
    parser.add_argument("--dashboard", choices=["auto", "streamlit", "curses", "none"], default="auto", help="Dashboard rendering backend")
    args = parser.parse_args()

    inp = args.inp or default_inp(args.mode, args.profile)
    if not inp:
        parser.error("Provide an input file or specify --mode and --profile")
    if not os.path.exists(inp):
        raise SystemExit(f"Input file not found: {inp}")

    cp2k = args.cp2k or which("cp2k.psmp") or which("cp2k")
    if not cp2k:
        raise SystemExit("cp2k not found on PATH")

    env = os.environ.copy()
    project = args.project or pathlib.Path(inp).stem
    env["PROJECT"] = project
    logfile = f"{project}.out"

    dashboard_mode = args.dashboard
    if args.no_dashboard:
        dashboard_mode = "none"

    if dashboard_mode == "auto":
        if which("streamlit"):
            dashboard_mode = "streamlit"
        elif _isatty():
            dashboard_mode = "curses"
        else:
            dashboard_mode = "none"

    state: Optional[RunState] = None
    input_render: List[str] = []
    streamlit_info: Optional[Dict[str, object]] = None

    if dashboard_mode in {"streamlit", "curses"}:
        state = RunState(project=project, logfile=logfile, input_path=inp, profile=args.profile, mode=args.mode)
        input_render = pretty_cp2k_input(inp)

    def make_runner(run_state: RunState) -> threading.Thread:
        def worker() -> None:
            try:
                run_cp2k_process(cp2k, inp, env, run_state)
            except Exception as exc:  # pragma: no cover - defensive
                run_state.append_tail(f"<dashboard error: {exc}>")
                run_state.finalize(return_code=1)

        thread = threading.Thread(target=worker, name="cp2k-runner", daemon=True)
        thread.start()
        return thread

    if dashboard_mode == "streamlit" and state is not None:
        streamlit_info = launch_streamlit(state, input_render)
        if not streamlit_info:
            print("Streamlit not available; falling back to curses dashboard.")
            dashboard_mode = "curses" if _isatty() else "none"

    if dashboard_mode == "streamlit" and state is not None:
        state.echo_to_stdout = True
        runner = make_runner(state)
        try:
            runner.join()
        finally:
            if streamlit_info and streamlit_info.get("process"):
                proc = streamlit_info["process"]
                assert isinstance(proc, subprocess.Popen)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            if streamlit_info and streamlit_info.get("dir"):
                temp_dir = streamlit_info["dir"]
                try:
                    import shutil

                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass
        return_code = state.return_code if state.return_code is not None else 1
    elif dashboard_mode == "curses" and state is not None and _isatty():
        runner = make_runner(state)
        dashboard_loop(state, input_render)
        runner.join()
        return_code = state.return_code if state.return_code is not None else 1
    else:
        if state is not None:
            state.set_state_file(None)
        return_code = basic_run(cp2k, inp, env, logfile)

    print(json.dumps({"project": project, "logfile": logfile, "return_code": return_code}))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
