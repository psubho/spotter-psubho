# Spotter — fuel-aware US driving route API

A small Django 6.1 API for the Backend Django Engineer assessment. Give it a US start and finish city; it returns a driving route as GeoJSON, suggested fuel stops from the supplied price file, and the amount spent on fuel bought during the trip.

## Run locally

Requires Python 3.12 or newer. Python 3.13 was used for development.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py load_fuel_data
python manage.py runserver
```

Ask for a route:

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H 'Content-Type: application/json' \
  -d '{"start":"Chicago, IL","finish":"Dallas, TX"}'
```

The response contains `route.distance_miles`, `route.duration_hours`, `route.geometry` (a GeoJSON LineString), `fuel.stops`, `fuel.gallons_purchased`, and `fuel.total_spent_usd`. The `GET /api/health/` endpoint reports whether reference data has been loaded.

Run tests with `python manage.py test`. The test suite mocks routing; it does not depend on internet access.

## Assumptions and cost model

- The vehicle gets **10 mpg**, has a **500-mile / 50-gallon capacity**, and **starts with a full tank**. These are constants in [`routes/fuel.py`](routes/fuel.py).
- `total_spent_usd` is the sum of purchases made after departure. The full starting tank is considered prepaid, so its cost is *not* charged again. `gallons_consumed` reports the trip's total fuel use separately.
- Fuel can be bought in fractional gallons. There is no mandated reserve. Prices in the supplied CSV are treated as USD per gallon and as a static snapshot.
- “Optimal” means minimum purchase cost **along the fixed returned route**, with no detour, stop-time, toll, tax, or trip-origin fuel cost. It does not compare alternate driving routes.
- Stops are approximate *city-level* locations. The supplied price file has city/state and street text, but no station coordinates. Each fuel city is represented by a postal-code centroid, so stop pins must not be used for turn-by-turn navigation. Candidates must be within 25 straight-line miles of the route; the reported distance from route is approximate. The closest city centroid to a route point defines the stop's mile marker.
- The cheapest priced station in each city is retained; the source has multiple stations in some cities but identical approximate city coordinates. Canadian rows are excluded because the brief calls for locations within the USA.
- City input uses `City, ST` (two-letter state code). This keeps the API deterministic without consuming an extra geocoding call.

## Design

1. `load_fuel_data` imports US places and the supplied fuel prices into SQLite. No runtime geocoding is needed.
2. The API resolves the requested cities locally, then makes **one OSRM route request** for an uncached origin/destination pair. The route geometry and distance are cached in process for 24 hours.
3. It samples the geometry roughly every three straight-line miles and uses a simple grid to find nearby fuel-city centroids.
4. On the ordered, fixed route, it buys only enough fuel to reach the next cheaper station within range; when none exists, it buys enough for the destination or fills the tank. A route with an unbridgeable station gap returns HTTP 422 instead of fabricating a feasible plan.

The API is deliberately synchronous and small. The assessment dataset has about 3,800 distinct US fuel cities; local route filtering avoids one call per station and keeps the external routing use to one call per uncached trip. A Chicago-to-Dallas check returned a 964-mile route with fuel stops in about 1.3 seconds on a development machine; that is a single observation, not a performance guarantee.

## Operational limits and possible improvements

The default public [OSRM demo server](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server) is suitable only for light, non-commercial evaluation: it has usage limits and no uptime guarantee. For production, use a hosted routing provider or self-host OSRM; set `OSRM_BASE_URL` accordingly. The current in-process cache is not shared between workers, so production deployments would use Redis or another shared cache and enforce rate limits. Set a strong `DJANGO_SECRET_KEY` and appropriate `DJANGO_ALLOWED_HOSTS` before deployment.

More importantly, precise recommendations need actual station latitude/longitude (or geocoded addresses), route detour distance/time, and ideally live prices. Those are not present in the input file. The response explicitly marks `location_precision` and `limitations` so clients do not mistake the city centroids for exact fuel pumps.

## Data attribution

- `data/fuel-prices.csv`: fuel-price assessment file supplied with the hiring exercise. Prices are a fixed snapshot, not live quotes.
- `data/geonames-US-postal.zip`: [GeoNames US postal data](https://download.geonames.org/export/zip/US.zip), licensed [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). GeoNames provides approximate postal-place centroids used for local city lookup and stop filtering.
- Driving routes: [OSRM](https://project-osrm.org/), called at runtime; routing map data is derived from [OpenStreetMap](https://www.openstreetmap.org/copyright).
