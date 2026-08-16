"""Shared Lightning Lane Multi Pass capacity-1 resource bookkeeping, used by
both GreedySolver and GreedyChallengeSolver so this constraint's state
machine isn't duplicated across solver strategies.
"""

from __future__ import annotations

from datetime import datetime

from optimized_experience.optimizer.contracts import LightningLaneHold, Node


def expire_if_needed(hold: LightningLaneHold | None, clock: datetime) -> LightningLaneHold | None:
    if hold is not None and hold.status == "BOOKED" and clock > hold.return_end:
        return LightningLaneHold(**{**hold.model_dump(), "status": "EXPIRED"})
    return hold


def is_held_by(hold: LightningLaneHold | None, node: Node) -> bool:
    return hold is not None and hold.node_id == node.id and hold.status == "BOOKED"


def is_resource_free(hold: LightningLaneHold | None) -> bool:
    return hold is None or hold.status in ("REDEEMED", "EXPIRED")


def mark_redeemed(hold: LightningLaneHold) -> LightningLaneHold:
    return LightningLaneHold(**{**hold.model_dump(), "status": "REDEEMED"})
