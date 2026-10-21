from decimal import Decimal

from django.test import SimpleTestCase

from routes.fuel import FuelPlanUnavailable, plan_fuel
from routes.geometry import StopCandidate


def candidate(mile: float, price: str, station_id: int) -> StopCandidate:
    return StopCandidate(
        station_id=station_id,
        opis_id=str(station_id),
        name=f"Station {station_id}",
        address="Test road",
        city="Test City",
        state="TX",
        latitude=0,
        longitude=0,
        price_per_gallon=Decimal(price),
        mile_marker=mile,
        distance_from_route_miles=0,
    )


class FuelPlannerTests(SimpleTestCase):
    def test_full_starting_tank_covers_short_route_without_purchase(self):
        result = plan_fuel(450, [candidate(200, "3.00", 1)])
        self.assertEqual(result.purchases, [])
        self.assertEqual(result.total_spent_usd, Decimal("0.00"))
        self.assertEqual(result.gallons_consumed, 45)

    def test_buys_only_enough_to_reach_cheaper_station(self):
        result = plan_fuel(
            800,
            [candidate(400, "4.00", 1), candidate(600, "3.00", 2)],
        )
        self.assertEqual([item.station.station_id for item in result.purchases], [1, 2])
        self.assertAlmostEqual(result.purchases[0].gallons, 10)
        self.assertAlmostEqual(result.purchases[1].gallons, 20)
        self.assertEqual(result.total_spent_usd, Decimal("100.00"))

    def test_cheapest_early_station_fills_tank_when_no_cheaper_station_ahead(self):
        result = plan_fuel(
            900,
            [candidate(400, "3.00", 1), candidate(600, "4.00", 2)],
        )
        self.assertEqual([item.station.station_id for item in result.purchases], [1])
        self.assertAlmostEqual(result.purchases[0].gallons, 40)
        self.assertEqual(result.total_spent_usd, Decimal("120.00"))

    def test_unbridgeable_gap_is_reported(self):
        with self.assertRaises(FuelPlanUnavailable):
            plan_fuel(1200, [candidate(600, "3.00", 1)])

    def test_no_station_needed_at_exact_500_miles(self):
        self.assertEqual(plan_fuel(500, []).purchases, [])

    def test_rejects_nonpositive_route(self):
        with self.assertRaises(ValueError):
            plan_fuel(0, [])
