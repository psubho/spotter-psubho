"""Offline US city lookup built from the bundled GeoNames postal-place data."""

import re
import unicodedata

from .models import City


US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


def normalize_city(value: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def resolve_location(value: object) -> City:
    """Resolve a `City, ST` string without any live geocoding request."""
    if not isinstance(value, str) or value.count(",") != 1:
        raise ValueError("Use a location in 'City, ST' format.")
    city_name, state = (part.strip() for part in value.split(",", maxsplit=1))
    state = state.upper()
    if not city_name or state not in US_STATE_CODES:
        raise ValueError("Use a valid US city and two-letter state code.")
    city = City.objects.filter(state=state, normalized_name=normalize_city(city_name)).first()
    if city is None:
        raise ValueError(f"US city not found: {city_name}, {state}.")
    return city
