"""Load the bundled fuel CSV and GeoNames postal places into SQLite."""

import csv
import statistics
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routes.locations import US_STATE_CODES, normalize_city
from routes.models import City, FuelStation


class Command(BaseCommand):
    help = "Replace the city and fuel-station reference data from the bundled source files."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--fuel-file", type=Path, default=settings.BASE_DIR / "data/fuel-prices.csv")
        parser.add_argument("--places-file", type=Path, default=settings.BASE_DIR / "data/geonames-US-postal.zip")

    def handle(self, *args, **options) -> None:
        fuel_path = options["fuel_file"]
        places_path = options["places_file"]
        if not fuel_path.is_file() or not places_path.is_file():
            raise CommandError("Both the fuel CSV and GeoNames US ZIP are required.")

        coordinates: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
        display_names: dict[tuple[str, str], str] = {}
        with ZipFile(places_path) as archive:
            with archive.open("US.txt") as source:
                lines = (line.decode("utf-8") for line in source)
                for row in csv.reader(lines, delimiter="\t"):
                    if len(row) < 11 or row[4] not in US_STATE_CODES or not row[9] or not row[10]:
                        continue
                    key = (normalize_city(row[2]), row[4])
                    coordinates[key].append((float(row[9]), float(row[10])))
                    display_names.setdefault(key, row[2])

        if not coordinates:
            raise CommandError("No US locations found in the GeoNames ZIP.")

        # A city can contain several ZIP-code centroids. The coordinate is an
        # approximation for route filtering, not a precise fuel-pump location.
        cities = [
            City(
                normalized_name=key[0],
                state=key[1],
                name=display_names[key],
                latitude=statistics.median(point[0] for point in points),
                longitude=statistics.median(point[1] for point in points),
            )
            for key, points in sorted(coordinates.items())
        ]

        with fuel_path.open(newline="", encoding="utf-8-sig") as source:
            rows = list(csv.DictReader(source))
        if not rows:
            raise CommandError("The fuel-price CSV is empty.")

        best_by_city: dict[tuple[str, str], tuple[Decimal, dict[str, str]]] = {}
        us_rows = 0
        for row in rows:
            state = row["State"].strip().upper()
            if state not in US_STATE_CODES:
                continue
            us_rows += 1
            key = (normalize_city(row["City"]), state)
            if key not in coordinates:
                raise CommandError(f"No city coordinate for {row['City']}, {state}.")
            try:
                price = Decimal(row["Retail Price"].strip())
            except InvalidOperation as exc:
                raise CommandError(f"Invalid fuel price for {row['Truckstop Name']}.") from exc
            if price <= 0:
                raise CommandError(f"Non-positive fuel price for {row['Truckstop Name']}.")
            if key not in best_by_city or price < best_by_city[key][0]:
                best_by_city[key] = (price, row)

        with transaction.atomic():
            FuelStation.objects.all().delete()
            City.objects.all().delete()
            City.objects.bulk_create(cities, batch_size=1000)
            ids = {(name, state): pk for pk, name, state in City.objects.values_list("id", "normalized_name", "state")}
            stations = [
                FuelStation(
                    city_id=ids[key],
                    opis_id=row["OPIS Truckstop ID"].strip(),
                    name=row["Truckstop Name"].strip(),
                    address=row["Address"].strip(),
                    rack_id=row["Rack ID"].strip(),
                    price_per_gallon=price,
                )
                for key, (price, row) in best_by_city.items()
            ]
            FuelStation.objects.bulk_create(stations, batch_size=1000)

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(cities)} US cities and the cheapest station in each of "
                f"{len(stations)} fuel-data cities ({us_rows} US price rows reviewed)."
            )
        )
