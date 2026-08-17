"""Walking-time estimation from real attraction coordinates. No new dependency
needed -- Coordinates.distance_miles() (contracts.py) already does the
haversine math; this module just converts distance to time via a
guest-selected walking pace.
"""

from __future__ import annotations

from optimized_experience.optimizer.contracts import Coordinates

# Documented estimates, not authoritative -- theme-park walking in a crowd is
# slower than open-road walking speed. Adjustable via preferences.walking_pace.
WALKING_PACE_MPH = {"SLOW": 2.0, "AVERAGE": 2.7, "FAST": 3.3}


def walk_minutes(a: Coordinates | None, b: Coordinates | None, pace_mph: float) -> float:
    """Missing location data is a documented simplification, not a crash: it's
    treated as zero walking cost rather than blocking scheduling."""
    if a is None or b is None:
        return 0.0
    return (a.distance_miles(b) / pace_mph) * 60.0
