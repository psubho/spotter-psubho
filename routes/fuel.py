"""Minimum-cost refuelling on a fixed, ordered route with a full starting tank."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .geometry import StopCandidate


MILES_PER_GALLON = 10.0
MAX_RANGE_MILES = 500.0
TANK_CAPACITY_GALLONS = MAX_RANGE_MILES / MILES_PER_GALLON
INITIAL_FUEL_GALLONS = TANK_CAPACITY_GALLONS
CENT = Decimal("0.01")
EPSILON = 1e-6


class FuelPlanUnavailable(Exception):
    pass


@dataclass(frozen=True)
class FuelPurchase:
    station: StopCandidate
    gallons: float
    cost_usd: Decimal


@dataclass(frozen=True)
class FuelPlan:
    purchases: list[FuelPurchase]
    total_spent_usd: Decimal
    gallons_purchased: float
    gallons_consumed: float


def plan_fuel(distance_miles: float, candidates: list[StopCandidate]) -> FuelPlan:
    """Buy just enough to reach a cheaper station; otherwise fill for the road ahead.

    This is optimal for a fixed path and prices when fuel can be bought in any
    amount, the tank has no reserve requirement, and detours are ignored.
    """
    if distance_miles <= 0:
        raise ValueError("The driving route must have a positive distance.")

    stations = sorted(candidates, key=lambda c: (c.mile_marker, c.price_per_gallon, c.station_id))
    fuel_remaining = INITIAL_FUEL_GALLONS
    current_mile = 0.0
    purchases: list[FuelPurchase] = []

    for index, station in enumerate(stations):
        if distance_miles - current_mile <= fuel_remaining * MILES_PER_GALLON + EPSILON:
            break
        gap = station.mile_marker - current_mile
        if gap < -EPSILON or station.mile_marker >= distance_miles:
            continue
        if gap > fuel_remaining * MILES_PER_GALLON + EPSILON:
            raise FuelPlanUnavailable("No supplied fuel station is reachable before the tank runs empty.")
        fuel_remaining = max(0.0, fuel_remaining - gap / MILES_PER_GALLON)
        current_mile = station.mile_marker

        if distance_miles - current_mile <= fuel_remaining * MILES_PER_GALLON + EPSILON:
            break

        next_cheaper = next(
            (
                later
                for later in stations[index + 1 :]
                if later.mile_marker - current_mile <= MAX_RANGE_MILES + EPSILON
                and later.price_per_gallon < station.price_per_gallon
            ),
            None,
        )
        if next_cheaper is not None:
            target_gallons = (next_cheaper.mile_marker - current_mile) / MILES_PER_GALLON
        else:
            target_gallons = min(TANK_CAPACITY_GALLONS, (distance_miles - current_mile) / MILES_PER_GALLON)

        gallons_to_buy = max(0.0, target_gallons - fuel_remaining)
        if gallons_to_buy <= EPSILON:
            continue
        fuel_remaining += gallons_to_buy
        cost = (Decimal(str(gallons_to_buy)) * station.price_per_gallon).quantize(CENT, rounding=ROUND_HALF_UP)
        purchases.append(FuelPurchase(station=station, gallons=gallons_to_buy, cost_usd=cost))

    if distance_miles - current_mile > fuel_remaining * MILES_PER_GALLON + EPSILON:
        raise FuelPlanUnavailable("The supplied stations leave an unbridgeable gap on this route.")

    return FuelPlan(
        purchases=purchases,
        total_spent_usd=sum((purchase.cost_usd for purchase in purchases), Decimal("0.00")),
        gallons_purchased=sum(purchase.gallons for purchase in purchases),
        gallons_consumed=distance_miles / MILES_PER_GALLON,
    )
