from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="City",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("normalized_name", models.CharField(max_length=180)),
                ("state", models.CharField(max_length=2)),
                ("latitude", models.FloatField()),
                ("longitude", models.FloatField()),
            ],
            options={
                "indexes": [models.Index(fields=["state", "normalized_name"], name="routes_city_state_a9aceb_idx")],
                "constraints": [models.UniqueConstraint(fields=("normalized_name", "state"), name="city_name_state_unique")],
            },
        ),
        migrations.CreateModel(
            name="FuelStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("opis_id", models.CharField(max_length=32)),
                ("name", models.CharField(max_length=255)),
                ("address", models.CharField(max_length=255)),
                ("rack_id", models.CharField(max_length=32)),
                ("price_per_gallon", models.DecimalField(decimal_places=8, max_digits=11)),
                ("city", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_stations", to="routes.city")),
            ],
            options={
                "indexes": [models.Index(fields=["city", "price_per_gallon"], name="routes_fuel_city_id_68ff99_idx")],
            },
        ),
    ]
