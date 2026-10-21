from django.db import models


class City(models.Model):
    name = models.CharField(max_length=180)
    normalized_name = models.CharField(max_length=180)
    state = models.CharField(max_length=2)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["normalized_name", "state"], name="city_name_state_unique")
        ]
        indexes = [models.Index(fields=["state", "normalized_name"])]

    def __str__(self) -> str:
        return f"{self.name}, {self.state}"


class FuelStation(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="fuel_stations")
    opis_id = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    rack_id = models.CharField(max_length=32)
    price_per_gallon = models.DecimalField(max_digits=11, decimal_places=8)

    class Meta:
        indexes = [models.Index(fields=["city", "price_per_gallon"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"
