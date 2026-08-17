"""Pydantic models mirroring the real shapes returned by api.themeparks.wiki/v1.

Field sets are trimmed to what the optimizer actually consumes; unknown fields
on the real API are ignored rather than rejected, since the upstream schema is
unofficial and can add fields without notice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EntityType = Literal["PARK", "ATTRACTION", "SHOW", "RESTAURANT", "HOTEL"]


class _LenientModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Location(_LenientModel):
    longitude: float
    latitude: float


class ChildEntity(_LenientModel):
    id: str
    name: str
    entityType: EntityType
    slug: str | None = None
    parentId: str | None = None
    location: Location | None = None


class ChildrenResponse(_LenientModel):
    id: str
    name: str
    entityType: EntityType
    timezone: str
    children: list[ChildEntity]


class StandbyQueue(_LenientModel):
    waitTime: int | None = None


class PriceInfo(_LenientModel):
    amount: int
    currency: str
    formatted: str


class ReturnTimeQueue(_LenientModel):
    state: Literal["AVAILABLE", "FINISHED", "TEMPORARILY_FULL", "NOT_YET_OPEN"] | None = None
    returnStart: datetime | None = None
    returnEnd: datetime | None = None
    price: PriceInfo | None = None  # only ever present on PAID_RETURN_TIME (Single Pass)


class Queue(_LenientModel):
    STANDBY: StandbyQueue | None = None
    RETURN_TIME: ReturnTimeQueue | None = None  # Lightning Lane Multi Pass
    PAID_RETURN_TIME: ReturnTimeQueue | None = None  # Lightning Lane Single Pass


class OperatingHoursPeriod(_LenientModel):
    type: str
    startTime: datetime
    endTime: datetime


class Showtime(_LenientModel):
    type: str | None = None
    startTime: datetime
    endTime: datetime


class ForecastEntry(_LenientModel):
    time: datetime
    waitTime: int | None = None


LiveStatus = Literal["OPERATING", "DOWN", "CLOSED", "REFURBISHMENT"]


class LiveDataEntry(_LenientModel):
    id: str
    name: str
    entityType: EntityType
    status: LiveStatus | None = None
    queue: Queue | None = None
    showtimes: list[Showtime] = []
    operatingHours: list[OperatingHoursPeriod] = []
    forecast: list[ForecastEntry] = []
    lastUpdated: datetime | None = None


class LiveResponse(_LenientModel):
    id: str
    liveData: list[LiveDataEntry]


class ScheduleEntry(_LenientModel):
    date: str
    type: str
    openingTime: datetime | None = None
    closingTime: datetime | None = None


class ScheduleResponse(_LenientModel):
    id: str
    timezone: str
    schedule: list[ScheduleEntry]
