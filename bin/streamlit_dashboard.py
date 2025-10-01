#!/usr/bin/env python3
"""Streamlit app for live CP2K dashboard."""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

STATE_PATH = os.environ.get("CP2K_DASHBOARD_STATE")
PROJECT = os.environ.get("CP2K_DASHBOARD_PROJECT", "CP2K Run")
REFRESH_MS = int(os.environ.get("CP2K_DASHBOARD_REFRESH_MS", "1000"))
INPUT_SNIPPET = os.environ.get("CP2K_DASHBOARD_INPUT", "")
LOGFILE = os.environ.get("CP2K_DASHBOARD_LOGFILE", "")
PROFILE = os.environ.get("CP2K_DASHBOARD_PROFILE", "-")
MODE = os.environ.get("CP2K_DASHBOARD_MODE", "-")

st.set_page_config(page_title=f"CP2K Dashboard: {PROJECT}", layout="wide")
st.title(f"CP2K Dashboard — {PROJECT}")

status_placeholder = st.empty()
meta_placeholder = st.empty()
table_placeholder = st.empty()
charts_placeholder = st.container()
refresh_col, cancel_col = st.columns([1, 1])
refresh_clicked = refresh_col.button("Refresh dashboard", type="primary")
input_expander = st.expander("Input summary", expanded=False)

if INPUT_SNIPPET:
    input_expander.text(INPUT_SNIPPET)
else:
    input_expander.info("Input preview not available.")

state_file = Path(STATE_PATH) if STATE_PATH else None


def load_state(path: Optional[Path]) -> Optional[Dict[str, object]]:
    if path is None or not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return None
    except OSError:
        return None


def render(state: Dict[str, object]) -> None:
    status = state.get("status", "unknown")
    runtime = state.get("runtime")
    return_code = state.get("return_code")
    pid = state.get("pid")
    status_placeholder.markdown(
        f"**Status:** `{status}` — **Runtime:** `{runtime:.1f}s` — **PID:** `{pid or '-'}" if runtime is not None else f"**Status:** `{status}`"
    )
    meta_placeholder.markdown(
        f"**Mode:** `{MODE}` · **Profile:** `{PROFILE}` · **Log file:** `{LOGFILE}`"
    )

    if status not in {"completed", "failed"} and pid:
        if cancel_col.button("Cancel CP2K run", key="cancel_button"):
            try:
                os.kill(int(pid), signal.SIGINT)
            except Exception as exc:  # pragma: no cover - UI feedback only
                st.warning(f"Failed to send cancel signal: {exc}")

    blocks: List[Dict[str, object]] = state.get("blocks", [])  # type: ignore[arg-type]
    if blocks:
        df = pd.DataFrame(blocks)
        if "step" in df.columns:
            df = df.sort_values("step")
        column_order = [
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
        existing = [c for c in column_order if c in df.columns]
        remaining = [c for c in df.columns if c not in existing]
        df = df[existing + remaining]
        table_placeholder.dataframe(df, use_container_width=True)

        numeric_cols = [c for c in df.columns if c not in {"step"} and pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols:
            idx_column = "time_fs" if "time_fs" in df.columns else "step"
            if idx_column in df.columns:
                chart_df = df.set_index(idx_column)
            else:
                chart_df = df.copy()
            charts_placeholder.subheader("Observables")
            for col in numeric_cols:
                if col not in chart_df.columns:
                    continue
                label = col.replace("_", " ").title()
                with charts_placeholder.container():
                    st.markdown(f"**{label}**")
                    st.line_chart(chart_df[[col]], height=220)
    else:
        table_placeholder.info("Waiting for MD steps...")


    if return_code is not None and status in {"completed", "failed"}:
        st.success(f"Run finished with return code {return_code}")


state = load_state(state_file)
if state:
    render(state)
else:
    status_placeholder.info("Waiting for CP2K output...")

if state and state.get("status") in {"completed", "failed"}:
    st.stop()

if refresh_clicked:
    _rerun = getattr(st, "experimental_rerun", None) or getattr(st, "rerun")
    _rerun()

if state and state.get("status") not in {"completed", "failed"}:
    time.sleep(max(REFRESH_MS, 200) / 1000.0)
    _rerun = getattr(st, "experimental_rerun", None) or getattr(st, "rerun")
    _rerun()
