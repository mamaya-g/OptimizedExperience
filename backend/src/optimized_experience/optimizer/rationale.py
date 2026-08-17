"""Plain-language, guest-facing justification for each scheduled step --
distinct from `PlanStep.rationale`, which mentions the solver by name and is
meant for a curious "how this is planned" panel, not the primary UI.

Runs as a post-processing pass over an already-solved Plan (see
`annotate_guest_rationale`), not inside any solver, so the same explanation
logic applies no matter which solver produced the plan. Deliberately
rule-based rather than an attempt to reverse-engineer the solver's actual
global optimization: OR-Tools' real reasoning is an opaque search over
thousands of combinations, not reducible to one sentence, so this instead
surfaces the specific real signals we *do* know about the chosen slot
(weather comfort, reliability timing, live wait, tier, Lightning Lane) --
honest about the mechanism, not a fabricated account of "why".
"""

from __future__ import annotations

from optimized_experience.data.preferences import WaterRideComfort
from optimized_experience.data.weather_client import HourlyWeather
from optimized_experience.optimizer.contracts import Node, Plan, PlanRequest, PlanStep
from optimized_experience.optimizer.scoring import (
    find_forecast_for_hour,
    reliability_factor,
    weather_comfort_factor,
)

# Matches preferences.py's PreferenceTier.MUST_GO prize (100.0) -- Node
# doesn't retain the raw tier enum, only the prize it produced, so this
# threshold is how a must-see pick is recognized after the fact.
_MUST_SEE_PRIZE_THRESHOLD = 100.0

_LOW_WAIT_THRESHOLD_MINUTES = 15.0


def guest_rationale_for_step(
    step: PlanStep,
    node: Node,
    hourly_forecast: list[HourlyWeather],
    water_ride_comfort: WaterRideComfort,
) -> str:
    if step.action == "DO_ACTIVITY":
        return f"Your requested {node.name.lower()}."

    if node.mandatory and node.kind == "SHOW":
        return f"You asked to catch {node.name}."

    if node.is_water_ride and water_ride_comfort is not WaterRideComfort.DONT_MIND:
        forecast = find_forecast_for_hour(hourly_forecast, step.planned_arrival)
        if forecast is not None:
            factor = weather_comfort_factor(True, forecast, water_ride_comfort)
            if factor > 1.0:
                return "Scheduled for the afternoon, once it's warmed up -- water rides are more fun once it's not cool out."
            if factor < 1.0:
                return "This was the best-fitting slot today, even though it's a little cool out for a water ride."

    if reliability_factor(node.reliability_tier, step.planned_arrival) > 1.0:
        return (
            f"Scheduled earlier in the day -- {node.name} has a higher-than-usual chance of "
            "unexpected downtime, so riding it now leaves time to retry later if it goes down."
        )

    if step.action == "REDEEM_LIGHTNING_LANE":
        if node.wait_estimate_minutes >= _LOW_WAIT_THRESHOLD_MINUTES:
            return f"Standby was running about {round(node.wait_estimate_minutes)} min -- Lightning Lane skips it."
        return "Used Lightning Lane to skip the standby line."

    if node.base_prize >= _MUST_SEE_PRIZE_THRESHOLD:
        return "One of your must-see picks."

    if step.action == "RIDE_STANDBY" and step.wait_minutes <= _LOW_WAIT_THRESHOLD_MINUTES:
        if step.wait_minutes < 1:
            return "Walk right on -- no wait right now."
        return f"Wait was only about {round(step.wait_minutes)} min right now -- a good time to hop on."

    if step.action == "WATCH_SHOW":
        return f"{node.name} was playing right where your route already had you."

    return "Fit well with the rest of today's route."


def annotate_guest_rationale(plan: Plan, request: PlanRequest) -> Plan:
    nodes_by_id = {node.id: node for node in request.candidate_nodes}
    annotated_steps: list[PlanStep] = []
    for step in plan.steps:
        node = nodes_by_id.get(step.node_id)
        if node is None:
            annotated_steps.append(step)
            continue
        text = guest_rationale_for_step(step, node, request.hourly_forecast, request.water_ride_comfort)
        annotated_steps.append(step.model_copy(update={"guest_rationale": text}))
    return plan.model_copy(update={"steps": annotated_steps})
