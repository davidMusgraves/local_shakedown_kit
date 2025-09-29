#!/usr/bin/env python3
"""Run CP2K and surface an interactive dashboard while the job is active."""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import signal
import subprocess
import sys
import threading
import time
import textwrap
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional


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


@dataclass
class MetricSeries:
    steps: List[int] = field(default_factory=list)
    energies: List[float] = field(default_factory=list)
    potentials: List[float] = field(default_factory=list)
    kinetics: List[float] = field(default_factory=list)
    temperatures: List[float] = field(default_factory=list)

    def append(self, key: str, step: Optional[int], value: float) -> None:
        if key == "step" and step is not None:
            self.steps.append(step)
        elif key == "potential":
            self.potentials.append(value)
        elif key == "kinetic":
            self.kinetics.append(value)
        elif key == "temperature":
            self.temperatures.append(value)
        elif key == "total_energy":
            self.energies.append(value)


class RunState:
    def __init__(self, project: str, logfile: str, input_path: str, profile: Optional[str], mode: Optional[str]):
        self.project = project
        self.logfile = logfile
        self.input_path = input_path
        self.profile = profile
        self.mode = mode
        self.tail: Deque[str] = deque(maxlen=100)
        self.metrics = MetricSeries()
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.status = "launching"
        self.return_code: Optional[int] = None
        self.pid: Optional[int] = None
        self.done = threading.Event()
        self.cancel_requested = False
        self._last_step: Optional[int] = None

    def runtime(self) -> float:
        return time.time() - self.start_time

    def snapshot(self) -> Dict[str, object]:
        with self.lock:
            data = {
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
                    "energies": list(self.metrics.energies),
                    "potentials": list(self.metrics.potentials),
                    "kinetics": list(self.metrics.kinetics),
                    "temperatures": list(self.metrics.temperatures),
                },
            }
        return data

    def append_tail(self, line: str) -> None:
        with self.lock:
            self.tail.append(line.rstrip("\n"))

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

    def request_cancel(self) -> None:
        with self.lock:
            self.cancel_requested = True

    def cancelled(self) -> bool:
        with self.lock:
            return self.cancel_requested

    def record_metric(self, key: str, value: float, step: Optional[int] = None) -> None:
        with self.lock:
            if step is not None:
                self._last_step = step
                if not self.metrics.steps or self.metrics.steps[-1] != step:
                    self.metrics.steps.append(step)
            if key == "potential":
                self.metrics.potentials.append(value)
            elif key == "kinetic":
                self.metrics.kinetics.append(value)
            elif key == "temperature":
                self.metrics.temperatures.append(value)
            elif key == "total_energy":
                self.metrics.energies.append(value)


def parse_line_for_metrics(line: str, state: RunState) -> None:
    text = line.strip()
    if not text:
        return
    lower = text.lower()

    if "md|" in text:
        if "step number" in text:
            parts = text.split()
            try:
                value = int(parts[-1])
            except (IndexError, ValueError):
                value = None
            if value is not None:
                state.record_metric("step", float(value), step=value)
        elif "potential energy" in text:
            numbers = [float(x) for x in text.split() if _is_float(x)]
            if numbers:
                state.record_metric("potential", numbers[0])
        elif "kinetic energy" in text:
            numbers = [float(x) for x in text.split() if _is_float(x)]
            if numbers:
                state.record_metric("kinetic", numbers[0])
        elif "temperature" in text:
            numbers = [float(x) for x in text.split() if _is_float(x)]
            if numbers:
                state.record_metric("temperature", numbers[0])
    elif "total energy" in lower and "scf" not in lower:
        numbers = [float(x) for x in text.split() if _is_float(x)]
        if numbers:
            state.record_metric("total_energy", numbers[-1])


def _is_float(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


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
                stdscr.addnstr(y, 0, line, width - 1)
                y += 1

            y += 1
            stdscr.addnstr(y, 0, "Input Summary", width - 1)
            y += 1
            max_input_height = max(4, height // 3)
            for idx in range(min(max_input_height, len(input_render))):
                stdscr.addnstr(y + idx, 2, input_render[idx], width - 4)
            y += max_input_height + 1

            metrics = snap["metrics"]
            stdscr.addnstr(y, 0, "Run Metrics", width - 1)
            y += 1
            md_steps = metrics["steps"]
            potentials = metrics["potentials"]
            temperatures = metrics["temperatures"]
            energies = metrics["energies"]
            latest_step = md_steps[-1] if md_steps else None
            latest_temp = temperatures[-1] if temperatures else None
            latest_pot = potentials[-1] if potentials else None
            latest_energy = energies[-1] if energies else None
            table_rows = [
                f"MD steps: {len(md_steps)}" + (f" (last {latest_step})" if latest_step is not None else ""),
                f"Temperature [K]: {latest_temp:.2f}" if latest_temp is not None else "Temperature [K]: -",
                f"Potential E [Ha]: {latest_pot:.6f}" if latest_pot is not None else "Potential E [Ha]: -",
                f"Total E [Ha]: {latest_energy:.6f}" if latest_energy is not None else "Total E [Ha]: -",
            ]
            for row in table_rows:
                stdscr.addnstr(y, 2, row, width - 4)
                y += 1

            chart_width = max(10, width - 4)
            if potentials:
                stdscr.addnstr(y, 2, f"Potential energy trend: {sparkline(potentials, min(chart_width, 60))}", width - 4)
                y += 1
            if temperatures:
                stdscr.addnstr(y, 2, f"Temperature trend:    {sparkline(temperatures, min(chart_width, 60))}", width - 4)
                y += 1

            y += 1
            stdscr.addnstr(y, 0, "Output Tail (last 100 lines)", width - 1)
            y += 1
            tail_lines = snap["tail"][-(height - y - 1):]
            for idx, line in enumerate(tail_lines):
                stdscr.addnstr(y + idx, 2, line, width - 4)

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

    use_dashboard = (not args.no_dashboard) and _isatty()

    if use_dashboard:
        state = RunState(project=project, logfile=logfile, input_path=inp, profile=args.profile, mode=args.mode)
        input_render = pretty_cp2k_input(inp)

        def worker() -> None:
            try:
                run_cp2k_process(cp2k, inp, env, state)
            except Exception as exc:  # pragma: no cover - defensive
                state.append_tail(f"<dashboard error: {exc}>")
                state.finalize(return_code=1)

        runner = threading.Thread(target=worker, name="cp2k-runner", daemon=True)
        runner.start()
        dashboard_loop(state, input_render)
        runner.join()
        return_code = state.return_code if state.return_code is not None else 1
    else:
        return_code = basic_run(cp2k, inp, env, logfile)

    print(json.dumps({"project": project, "logfile": logfile, "return_code": return_code}))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
