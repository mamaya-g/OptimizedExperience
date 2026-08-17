"""Land-aware navigation, consulted by both greedy solvers (same sharing
pattern as lightning_lane.py) so the three navigation strategies don't
require a combinatorial explosion of new solver classes for 2 objectives x
3 strategies.
"""

from __future__ import annotations

from optimized_experience.optimizer.contracts import Node

# CLUSTERED only: extra cost for switching lands from the last-visited node,
# biasing the solver to stay geographically clustered without forbidding a
# high-value cross-land jump outright (that's the difference from LAND_ORDER).
LAND_SWITCH_PENALTY_MINUTES = 8.0


def is_eligible_under_land_order(node: Node, restricted_land: str | None) -> bool:
    """LAND_ORDER: eligible if the node is in the land the solver is
    currently restricted to (see land_order_index state in each solver), or
    its land is unmapped (a gap in the hand-seeded data should never
    hard-block scheduling), or it's a mandatory block (an already-committed
    Lightning Lane hold or a fixed-time meal is never blocked by land
    sequencing). `restricted_land=None` means unrestricted (e.g. land_order
    wasn't set, or its list is exhausted)."""
    return restricted_land is None or node.mandatory or node.land is None or node.land == restricted_land


def navigation_cost_minutes(
    strategy: str, previous_land: str | None, node_land: str | None, base_walk_minutes: float
) -> float:
    if strategy == "CLUSTERED" and previous_land is not None and node_land is not None and previous_land != node_land:
        return base_walk_minutes + LAND_SWITCH_PENALTY_MINUTES
    return base_walk_minutes
