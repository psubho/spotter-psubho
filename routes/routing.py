"""One OSRM Directions request per uncached pair of coordinates."""

import json
import urllib.error
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    pass


@dataclass(frozen=True)
class Route:
    distance_miles: float
    duration_seconds: float
    coordinates: list[list[float]]  # GeoJSON [longitude, latitude]


def fetch_route(start: tuple[float, float], finish: tuple[float, float]) -> Route:
    """Fetch a driving route; start/finish are (longitude, latitude)."""
    cache_key = (
        f"osrm:v1:{start[0]:.5f},{start[1]:.5f}:"
        f"{finish[0]:.5f},{finish[1]:.5f}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    coordinates = f"{start[0]:.6f},{start[1]:.6f};{finish[0]:.6f},{finish[1]:.6f}"
    params = urlencode({"overview": "full", "geometries": "geojson", "steps": "false"})
    url = f"{settings.OSRM_BASE_URL.rstrip('/')}/route/v1/driving/{coordinates}?{params}"
    request = Request(url, headers={"User-Agent": "spotter-psubho-assessment/1.0"})
    try:
        with urlopen(request, timeout=settings.OSRM_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (TimeoutError, urllib.error.URLError, OSError, ValueError) as exc:
        raise RoutingError("The routing service is currently unavailable.") from exc

    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RoutingError("No driving route was found between these locations.")
    raw_route = payload["routes"][0]
    geometry = raw_route.get("geometry", {})
    points = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if (
        not isinstance(points, list)
        or len(points) < 2
        or not isinstance(raw_route.get("distance"), (float, int))
        or raw_route["distance"] <= 0
    ):
        raise RoutingError("The routing service returned an incomplete route.")

    route = Route(
        distance_miles=raw_route["distance"] / METERS_PER_MILE,
        duration_seconds=float(raw_route.get("duration", 0)),
        coordinates=points,
    )
    cache.set(cache_key, route)
    return route
