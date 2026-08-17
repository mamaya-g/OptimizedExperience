"""The entire mechanism for swapping solvers: a name -> Solver lookup. Adding
a new solver means adding a branch here, not touching callers.
"""

from __future__ import annotations

from typing import Literal

from optimized_experience.optimizer.contracts import Objective, Solver
from optimized_experience.optimizer.greedy import GreedySolver
from optimized_experience.optimizer.greedy_challenge import GreedyChallengeSolver
from optimized_experience.optimizer.ortools_solver import ORToolsSolver

SolverName = Literal["greedy", "ortools"]


def get_solver(objective: Objective, solver_name: SolverName = "greedy") -> Solver:
    if solver_name == "ortools":
        return ORToolsSolver()
    if solver_name == "greedy":
        if objective == "MAXIMIZE_PRIZE":
            return GreedySolver()
        if objective == "ALL_RIDES_CHALLENGE":
            return GreedyChallengeSolver()
        raise ValueError(f"Unknown objective: {objective}")
    raise ValueError(f"Unknown solver: {solver_name}")
