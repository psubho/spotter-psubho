"""JSON endpoints for health and fuel-aware route planning."""

import json
from json import JSONDecodeError

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .fuel import (
    INITIAL_FUEL_GALLONS,
    MAX_RANGE_MILES,
    MILES_PER_GALLON,
    TANK_CAPACITY_GALLONS,
    FuelPlanUnavailable,
    plan_fuel,
)
from .geometry import find_route_stations
from .locations import resolve_location
from .models import City, FuelStation
from .routing import RoutingError, fetch_route


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    ready = City.objects.exists() and FuelStation.objects.exists()
    return JsonResponse({"status": "ok" if ready else "data_not_loaded"}, status=200 if ready else 503)


@csrf_exempt
@require_POST
def plan_route(request: HttpRequest) -> JsonResponse:
    if len(request.body) > 4096:
        return JsonResponse({"error": "Request body is too large."}, status=413)
    try:
        payload = json.loads(request.body)
    except (JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Send a JSON object with start and finish locations."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "The request body must be a JSON object."}, status=400)

    if not City.objects.exists() or not FuelStation.objects.exists():
        return JsonResponse({"error": "Reference data is not loaded. Run load_fuel_data."}, status=503)

    try:
        start = resolve_location(payload.get("start"))
        finish = resolve_location(payload.get("finish"))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    if start.pk == finish.pk:
        return JsonResponse({"error": "Start and finish must be different cities."}, status=400)

    try:
        route = fetch_route(
            (start.longitude, start.latitude),
            (finish.longitude, finish.latitude),
        )
    except RoutingError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    stations = list(FuelStation.objects.select_related("city"))
    candidates = find_route_stations(route, stations)
    try:
        fuel_plan = plan_fuel(route.distance_miles, candidates)
    except FuelPlanUnavailable as exc:
        return JsonResponse(
            {
                "error": str(exc),
                "route_distance_miles": round(route.distance_miles, 2),
                "candidate_stations_near_route": len(candidates),
            },
            status=422,
        )

    return JsonResponse(
        {
            "start": {"city": start.name, "state": start.state},
            "finish": {"city": finish.name, "state": finish.state},
            "route": {
                "distance_miles": round(route.distance_miles, 2),
                "duration_hours": round(route.duration_seconds / 3600, 2),
                "geometry": {"type": "LineString", "coordinates": route.coordinates},
            },
            "fuel": {
                "mpg": MILES_PER_GALLON,
                "maximum_range_miles": MAX_RANGE_MILES,
                "tank_capacity_gallons": TANK_CAPACITY_GALLONS,
                "starting_fuel_gallons": INITIAL_FUEL_GALLONS,
                "gallons_consumed": round(fuel_plan.gallons_consumed, 3),
                "gallons_purchased": round(fuel_plan.gallons_purchased, 3),
                "total_spent_usd": float(fuel_plan.total_spent_usd),
                "stops": [
                    {
                        "opis_id": purchase.station.opis_id,
                        "name": purchase.station.name,
                        "address": purchase.station.address,
                        "city": purchase.station.city,
                        "state": purchase.station.state,
                        "mile_marker": round(purchase.station.mile_marker, 1),
                        "approx_distance_from_route_miles": round(purchase.station.distance_from_route_miles, 1),
                        "location": {
                            "type": "Point",
                            "coordinates": [purchase.station.longitude, purchase.station.latitude],
                        },
                        "price_per_gallon_usd": float(purchase.station.price_per_gallon),
                        "gallons": round(purchase.gallons, 3),
                        "cost_usd": float(purchase.cost_usd),
                    }
                    for purchase in fuel_plan.purchases
                ],
            },
            "location_precision": "city_centroid_estimate",
            "cost_basis": "Fuel bought after departure; the full starting tank is pre-paid and excluded.",
            "limitations": [
                "Stop coordinates are city-level estimates, not exact truck-stop locations.",
                "Detour distance and fuel are not included in stop optimization or cost.",
            ],
        }
    )
