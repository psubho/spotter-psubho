import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from routes.geometry import find_route_stations
from routes.models import City, FuelStation
from routes.routing import Route, RoutingError, fetch_route


class RouteApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.start = City.objects.create(
            name="Startville", normalized_name="startville", state="TX", latitude=30.0, longitude=-100.0
        )
        cls.middle = City.objects.create(
            name="Midville", normalized_name="midville", state="TX", latitude=30.0, longitude=-95.0
        )
        cls.finish = City.objects.create(
            name="Endville", normalized_name="endville", state="TX", latitude=30.0, longitude=-90.0
        )
        FuelStation.objects.create(
            city=cls.middle, opis_id="123", name="Middle Fuel", address="Main Street",
            rack_id="R1", price_per_gallon=Decimal("3.25000000"),
        )

    def post(self, payload):
        return self.client.post("/api/route/", data=json.dumps(payload), content_type="application/json")

    def test_health_ready(self):
        self.assertEqual(self.client.get("/api/health/").json(), {"status": "ok"})

    @patch("routes.views.fetch_route")
    def test_route_response_includes_map_and_cost(self, mocked_route):
        mocked_route.return_value = Route(
            distance_miles=800,
            duration_seconds=12 * 3600,
            coordinates=[[-100.0, 30.0], [-95.0, 30.0], [-90.0, 30.0]],
        )
        response = self.post({"start": "Startville, TX", "finish": "Endville, TX"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["route"]["geometry"]["type"], "LineString")
        self.assertEqual(len(data["fuel"]["stops"]), 1)
        self.assertEqual(data["fuel"]["stops"][0]["opis_id"], "123")
        self.assertEqual(data["fuel"]["starting_fuel_gallons"], 50)
        self.assertGreater(data["fuel"]["total_spent_usd"], 0)
        mocked_route.assert_called_once()

    @patch("routes.views.fetch_route")
    def test_invalid_location_does_not_call_routing_provider(self, mocked_route):
        response = self.post({"start": "Paris, FR", "finish": "Endville, TX"})
        self.assertEqual(response.status_code, 400)
        mocked_route.assert_not_called()

    @patch("routes.views.fetch_route")
    def test_unreachable_station_returns_422(self, mocked_route):
        mocked_route.return_value = Route(
            distance_miles=1100,
            duration_seconds=60000,
            coordinates=[[-100, 30], [-95, 30], [-90, 30]],
        )
        response = self.post({"start": "Startville, TX", "finish": "Endville, TX"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("error", response.json())

    def test_bad_json(self):
        response = self.client.post("/api/route/", data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch("routes.views.fetch_route", side_effect=RoutingError("Routing unavailable"))
    def test_routing_failure(self, _mocked_route):
        response = self.post({"start": "Startville, TX", "finish": "Endville, TX"})
        self.assertEqual(response.status_code, 502)

    def test_city_centroid_is_detected_near_route(self):
        route = Route(800, 40000, [[-100, 30], [-95, 30], [-90, 30]])
        stations = list(FuelStation.objects.select_related("city"))
        self.assertEqual(find_route_stations(route, stations)[0].opis_id, "123")


class RoutingClientTests(SimpleTestCase):
    def tearDown(self):
        cache.clear()

    @patch("routes.routing.urlopen")
    def test_uses_one_provider_call_and_caches_repeat(self, mocked_open):
        from io import BytesIO

        body = json.dumps({
            "code": "Ok",
            "routes": [{"distance": 160934.4, "duration": 7200, "geometry": {
                "type": "LineString", "coordinates": [[-100.0, 30.0], [-99.0, 30.0]]
            }}],
        }).encode()
        mocked_open.return_value.__enter__.return_value = BytesIO(body)
        first = fetch_route((-100.0, 30.0), (-99.0, 30.0))
        second = fetch_route((-100.0, 30.0), (-99.0, 30.0))
        self.assertEqual(first.distance_miles, 100)
        self.assertEqual(first, second)
        mocked_open.assert_called_once()
