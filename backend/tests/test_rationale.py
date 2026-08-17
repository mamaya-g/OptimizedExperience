from datetime import datetime

from optimized_experience.data.preferences import WaterRideComfort
from optimized_experience.data.weather_client import HourlyWeather
from optimized_experience.optimizer.contracts import PlanStep
from optimized_experience.optimizer.rationale import guest_rationale_for_step

from conftest import make_activity, make_attraction, make_show

DAY = datetime(2026, 8, 16)


def make_step(
    node_id: str,
    node_name: str,
    action: str,
    hour: int,
    wait_minutes: float = 10.0,
    service_minutes: float = 5.0,
) -> PlanStep:
    arrival = DAY.replace(hour=hour)
    return PlanStep(
        node_id=node_id,
        node_name=node_name,
        action=action,
        planned_arrival=arrival,
        planned_departure=arrival,
        rationale="internal solver prose",
        wait_minutes=wait_minutes,
        service_minutes=service_minutes,
    )


def test_activity_block_rationale_names_the_request():
    node = make_activity("activity-0-Lunch", name="Lunch")
    step = make_step(node.id, node.name, "DO_ACTIVITY", hour=12)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert text == "Your requested lunch."


def test_mandatory_show_rationale_names_the_show():
    node = make_show("paint-the-night", name="Paint the Night", base_prize=100_000.0)
    node = node.model_copy(update={"mandatory": True})
    step = make_step(node.id, node.name, "WATCH_SHOW", hour=21)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert text == "You asked to catch Paint the Night."


def test_water_ride_boosted_afternoon_slot_explains_weather_timing():
    node = make_attraction("tianas", name="Tiana's Bayou Adventure", is_water_ride=True)
    step = make_step(node.id, node.name, "RIDE_STANDBY", hour=14, wait_minutes=20)
    forecast = [HourlyWeather(hour=DAY.replace(hour=14), temperature_f=80.0, short_forecast="Sunny")]
    text = guest_rationale_for_step(step, node, forecast, WaterRideComfort.PREFER_AFTERNOON)
    assert "afternoon" in text.lower()
    assert "warmed up" in text.lower()


def test_water_ride_discounted_slot_is_still_explained_honestly():
    node = make_attraction("tianas", name="Tiana's Bayou Adventure", is_water_ride=True)
    step = make_step(node.id, node.name, "RIDE_STANDBY", hour=9, wait_minutes=20)
    forecast = [HourlyWeather(hour=DAY.replace(hour=9), temperature_f=60.0, short_forecast="Cloudy")]
    text = guest_rationale_for_step(step, node, forecast, WaterRideComfort.MIND_IF_COOL)
    assert "best-fitting slot" in text.lower()


def test_low_reliability_morning_slot_explains_downtime_hedge():
    node = make_attraction("indyjones", name="Indiana Jones Adventure", reliability_tier="LOW")
    step = make_step(node.id, node.name, "RIDE_STANDBY", hour=9, wait_minutes=20)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert "unexpected downtime" in text.lower()


def test_lightning_lane_redeem_mentions_standby_wait_saved():
    node = make_attraction("riseoftheresistance", name="Rise of the Resistance", wait_estimate_minutes=45.0)
    step = make_step(node.id, node.name, "REDEEM_LIGHTNING_LANE", hour=13, wait_minutes=0)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert "45 min" in text
    assert "Lightning Lane" in text


def test_must_see_tier_rationale():
    node = make_attraction("spacemountain", name="Space Mountain", base_prize=100.0, wait_estimate_minutes=30.0)
    step = make_step(node.id, node.name, "RIDE_STANDBY", hour=13, wait_minutes=30)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert text == "One of your must-see picks."


def test_low_current_wait_rationale_for_untiered_attraction():
    node = make_attraction("autopia", name="Autopia", base_prize=10.0)
    step = make_step(node.id, node.name, "RIDE_STANDBY", hour=13, wait_minutes=5)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert "5 min" in text


def test_zero_wait_gets_walk_on_phrasing_not_zero_min():
    node = make_attraction("autopia", name="Autopia", base_prize=10.0)
    step = make_step(node.id, node.name, "RIDE_STANDBY", hour=13, wait_minutes=0)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert text == "Walk right on -- no wait right now."


def test_generic_fallback_for_unremarkable_step():
    node = make_attraction("junglecruise", name="Jungle Cruise", base_prize=10.0)
    step = make_step(node.id, node.name, "RIDE_STANDBY", hour=13, wait_minutes=30)
    text = guest_rationale_for_step(step, node, [], WaterRideComfort.MIND_IF_COOL)
    assert text == "Fit well with the rest of today's route."
