# Generated by Django 5.0.6 on 2024-07-11 18:13

import apps.uptime.models
import django.core.validators
from django.db import migrations, models


def migrate_interval_to_positive_int(apps, schema_editor):
    Monitor = apps.get_model("uptime", "Monitor")
    for monitor in Monitor.objects.all():
        monitor.interval = monitor.interval_old.seconds
        monitor.save()


class Migration(migrations.Migration):
    dependencies = [
        ("uptime", "0001_squashed_0008_statuspage_statuspage_unique_organization_slug"),
    ]

    operations = [
        migrations.RenameField(
            model_name="monitor",
            old_name="interval",
            new_name="interval_old",
        ),
        migrations.AddField(
            model_name="monitor",
            name="interval",
            field=models.PositiveSmallIntegerField(
                default=60,
                validators=[
                    django.core.validators.MaxValueValidator(86400),
                    django.core.validators.MinValueValidator(1),
                ],
            ),
        ),
        migrations.RemoveField(
            model_name="monitor",
            name="interval_old",
        ),
        migrations.AlterField(
            model_name="monitor",
            name="monitor_type",
            field=models.CharField(
                choices=[
                    ("Ping", "Ping"),
                    ("GET", "Get"),
                    ("POST", "Post"),
                    ("TCP Port", "Port"),
                    ("SSL", "Ssl"),
                    ("Heartbeat", "Heartbeat"),
                ],
                default="Ping",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="monitor",
            name="url",
            field=models.CharField(
                blank=True,
                max_length=2000,
                validators=[apps.uptime.models.OptionalSchemeURLValidator()],
            ),
        ),
    ]
