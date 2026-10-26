"""The owner's starting prices (24 Oct 2026). Adjusted later in the console."""

from django.db import migrations

BANDS = [
    ("band_1", "Up to 1,000 pupils", 1000, 25_000),
    ("band_2", "1,001 to 2,000 pupils", 2000, 35_000),
    ("band_3", "More than 2,000 pupils", None, 45_000),
]


def seed(apps, schema_editor):
    band = apps.get_model("control_plane", "PriceBandSetting")
    for position, (code, label, max_pupils, price) in enumerate(BANDS):
        band.objects.get_or_create(
            code=code,
            defaults={"label": label, "max_pupils": max_pupils, "price_pesewas": price, "position": position},
        )


class Migration(migrations.Migration):
    dependencies = [("control_plane", "0007_console_billing_announcements_problems")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
