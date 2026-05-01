"""Daily progress tracker for DustOps AI.

Run at the start of each work session to see current phase and status.
Phase state is stored in .progress_state.json (gitignored once git lands).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / ".progress_state.json"

PHASES = [
    ("A", "Architecture Constitution"),
    ("B", "Repo Scaffold"),
    ("C", "Data Harness"),
    ("D", "Mine State Engine"),
    ("E", "Forecasting MVP"),
    ("F", "Source Attribution"),
    ("G", "Intervention Simulation"),
    ("H", "Recommendation Engine"),
    ("I", "Human Approval Workflow"),
    ("J", "Dashboard"),
    ("K", "Feedback, Reporting, ROI"),
]

DASH = " - "


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"current_phase": "A", "completed_phases": []}


def main() -> None:
    state = load_state()
    today = date.today().isoformat()
    current = state["current_phase"]
    completed = set(state["completed_phases"])

    print("DustOps AI - progress")
    print(f"  date:           {today}")
    print(f"  current phase:  {current}")
    print()
    print("phase status:")
    for code, name in PHASES:
        if code in completed:
            mark = "[x]"
        elif code == current:
            mark = "[>]"
        else:
            mark = "[ ]"
        print(f"  {mark} {code}{DASH}{name}")
    print()
    print("next step: read docs/normalization_report.md and the active phase plan")


if __name__ == "__main__":
    main()
