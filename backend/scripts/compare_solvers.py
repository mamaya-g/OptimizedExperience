#!/usr/bin/env python
"""The actual portfolio artifact: runs the greedy heuristic and the OR-Tools
routing solver on the exact same day (recorded fixture data) and prints
total prize + wall-clock solve time side by side.

The greedy is a fast, single-pass, myopic heuristic. The OR-Tools solver is a
genuine global search (real travel time between attractions, a proper
prize-collecting VRPTW formulation) -- see optimizer/ortools_solver.py's
docstring for the documented simplifications it makes to stay tractable
(Lightning Lane's book/redeem two-step collapses into one visit; prize/wait
are fixed per node rather than dynamically re-derived). OR-Tools should never
score worse than the greedy on the same input -- that's the actual thing
being demonstrated here, not just "which is faster."

Run from backend/: PYTHONPATH=src .venv/bin/python scripts/compare_solvers.py
"""

from __future__ import annotations

import time
from pathlib import Path

from optimized_experience.cli import DEFAULT_CONFIG_DIR, build_sources, generate_plan
from optimized_experience.data.lands import load_land_map
from optimized_experience.data.preferences import load_preferences
from optimized_experience.data.reliability import load_reliability_profile

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "disneyland_aug16"

SOLVERS = [("greedy", "Greedy (myopic heuristic)"), ("ortools", "OR-Tools (global routing search)")]


def main() -> None:
    preferences = load_preferences(DEFAULT_CONFIG_DIR / "preferences.yaml")
    reliability_profile = load_reliability_profile(DEFAULT_CONFIG_DIR / "reliability_profile.yaml")
    land_map = load_land_map(DEFAULT_CONFIG_DIR / "land_map.yaml")

    print(f"\n{'Solver':<32}{'Total prize':>14}{'Steps':>10}{'Solve time':>14}")
    print("-" * 70)
    for solver_name, label in SOLVERS:
        data_source, weather_source = build_sources(FIXTURE_DIR)
        started = time.perf_counter()
        plan, _ = generate_plan(
            "MAXIMIZE_PRIZE",
            data_source,
            weather_source,
            preferences,
            reliability_profile,
            start_time_override=None,
            is_replay=True,
            land_map=land_map,
            solver_name=solver_name,
        )
        elapsed = time.perf_counter() - started
        print(f"{label:<32}{plan.total_prize:>14.1f}{len(plan.steps):>10}{elapsed:>13.2f}s")

    print(
        "\nOR-Tools' documented simplifications (see optimizer/ortools_solver.py): "
        "prize/wait fixed per node at its earliest feasible time rather than dynamically "
        "re-derived; Lightning Lane's book-then-redeem two-step collapses into a single "
        "visit. The greedy remains the mechanically fuller model -- this comparison is "
        "about solution quality (total prize) under a real, provably-searched global "
        "routing formulation, not full fidelity.\n"
    )


if __name__ == "__main__":
    main()
