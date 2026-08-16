"""The entire mechanism for swapping solvers: a name -> Solver lookup. Adding
an OR-Tools solver later means adding a branch here, not touching callers.
"""

from __future__ import annotations

from optimized_experience.optimizer.contracts import Objective, Solver
from optimized_experience.optimizer.greedy import GreedySolver
from optimized_experience.optimizer.greedy_challenge import GreedyChallengeSolver


def get_solver(objective: Objective) -> Solver:
    if objective == "MAXIMIZE_PRIZE":
        return GreedySolver()
    if objective == "ALL_RIDES_CHALLENGE":
        return GreedyChallengeSolver()
    raise ValueError(f"Unknown objective: {objective}")
