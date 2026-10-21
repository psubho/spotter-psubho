"""Approximate city positions along an OSRM route without additional API calls."""

import math
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from .models import FuelStation
from .routing import Route


EARTH_RADIUS_MILES = 3958.7613
MAX_CITY_TO_ROUTE_MILES = 25.0
SAMPLE_SPACING_MILES = 3.0
GRID_DEGREES = 0.25


@dataclass(frozen=True)
class RouteSample:
    latitude: float
    longitude: float
    mile_marker: float


@dataclass(frozen=True)
class StopCandidate:
    station_id: int
    opis_id: str
    name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    price_per_gallon: Decimal
    mile_marker: float
    distance_from_route_miles: float


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between (latitude, longitude) pairs."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def sample_route(route: Route) -> list[RouteSample]:
    """Sample the route geometry at short intervals for fast spatial matching."""
    points = route.coordinates
    segments = [
        haversine_miles((a[1], a[0]), (b[1], b[0]))
        for a, b in zip(points, points[1:])
    ]
    geometry_miles = sum(segments)
    if geometry_miles <= 0:
        return []

    samples = [RouteSample(points[0][1], points[0][0], 0.0)]
    next_sample = SAMPLE_SPACING_MILES
    elapsed = 0.0
    for (start, finish), segment_miles in zip(zip(points, points[1:]), segments):
        if segment_miles <= 0:
            continue
        while next_sample <= elapsed + segment_miles:
            fraction = (next_sample - elapsed) / segment_miles
            samples.append(
                RouteSample(
                    latitude=start[1] + fraction * (finish[1] - start[1]),
                    longitude=start[0] + fraction * (finish[0] - start[0]),
                    mile_marker=next_sample / geometry_miles * route.distance_miles,
                )
            )
            next_sample += SAMPLE_SPACING_MILES
        elapsed += segment_miles
    samples.append(RouteSample(points[-1][1], points[-1][0], route.distance_miles))
    return samples


def find_route_stations(route: Route, stations: list[FuelStation]) -> list[StopCandidate]:
    samples = sample_route(route)
    if not samples:
        return []

    grid: dict[tuple[int, int], list[RouteSample]] = defaultdict(list)
    for sample in samples:
        grid[(math.floor(sample.latitude / GRID_DEGREES), math.floor(sample.longitude / GRID_DEGREES))].append(sample)

    candidates: list[StopCandidate] = []
    latitude_span = MAX_CITY_TO_ROUTE_MILES / 69.0
    for station in stations:
        city = station.city
        longitude_span = MAX_CITY_TO_ROUTE_MILES / max(1.0, 69.0 * math.cos(math.radians(city.latitude)))
        nearby: list[RouteSample] = []
        for lat_cell in range(
            math.floor((city.latitude - latitude_span) / GRID_DEGREES),
            math.floor((city.latitude + latitude_span) / GRID_DEGREES) + 1,
        ):
            for lon_cell in range(
                math.floor((city.longitude - longitude_span) / GRID_DEGREES),
                math.floor((city.longitude + longitude_span) / GRID_DEGREES) + 1,
            ):
                nearby.extend(grid.get((lat_cell, lon_cell), ()))
        if not nearby:
            continue
        nearest = min(
            nearby,
            key=lambda sample: haversine_miles(
                (city.latitude, city.longitude), (sample.latitude, sample.longitude)
            ),
        )
        distance = haversine_miles(
            (city.latitude, city.longitude), (nearest.latitude, nearest.longitude)
        )
        if distance > MAX_CITY_TO_ROUTE_MILES or nearest.mile_marker >= route.distance_miles:
            continue
        candidates.append(
            StopCandidate(
                station_id=station.pk,
                opis_id=station.opis_id,
                name=station.name,
                address=station.address,
                city=city.name,
                state=city.state,
                latitude=city.latitude,
                longitude=city.longitude,
                price_per_gallon=station.price_per_gallon,
                mile_marker=nearest.mile_marker,
                distance_from_route_miles=distance,
            )
        )
    return sorted(candidates, key=lambda item: (item.mile_marker, item.price_per_gallon, item.station_id))
