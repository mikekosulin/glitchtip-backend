# Generated by Django 5.0.7 on 2024-07-12 19:00

import django.db.models.deletion
import django.utils.timezone
import psqlextra.backend.migrations.operations.add_default_partition
import psqlextra.backend.migrations.operations.create_partitioned_model
import psqlextra.manager.manager
import psqlextra.models.partitioned
import psqlextra.types
from django.db import migrations, models
from glitchtip.model_utils import TestDefaultPartition

from .functions.partition import create_partitions


class Migration(migrations.Migration):
    dependencies = [
        ("uptime", "0009_alter_monitor_interval_alter_monitor_monitor_type_and_more"),
        ("performance", "0014_initial"),
    ]

    operations = [
        psqlextra.backend.migrations.operations.create_partitioned_model.PostgresCreatePartitionedModel(
            name="MonitorCheck",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("is_up", models.BooleanField()),
                (
                    "is_change",
                    models.BooleanField(
                        help_text="Indicates change to is_up status for associated monitor"
                    ),
                ),
                (
                    "start_check",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        help_text="Time when the start of this check was performed",
                    ),
                ),
                (
                    "reason",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        choices=[
                            (0, "Unknown"),
                            (1, "Timeout"),
                            (2, "Wrong status code"),
                            (3, "Expected response not found"),
                            (4, "SSL error"),
                            (5, "Network error"),
                        ],
                        default=0,
                        null=True,
                    ),
                ),
                (
                    "response_time",
                    models.PositiveIntegerField(
                        blank=True, help_text="Reponse time in milliseconds", null=True
                    ),
                ),
                ("data", models.JSONField(blank=True, null=True)),
                (
                    "monitor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="checks",
                        to="uptime.monitor",
                    ),
                ),
            ],
            options={
                "ordering": ("-start_check",),
                "indexes": [
                    models.Index(
                        fields=["monitor", "-start_check"],
                        name="uptime_moni_monitor_a89b32_idx",
                    ),
                    models.Index(
                        fields=["monitor", "is_change", "-start_check"],
                        name="uptime_moni_monitor_b6d442_idx",
                    ),
                ],
            },
            partitioning_options={
                "method": psqlextra.types.PostgresPartitioningMethod["RANGE"],
                "key": ["start_check"],
            },
            bases=(psqlextra.models.partitioned.PostgresPartitionedModel,),
            managers=[
                ("objects", psqlextra.manager.manager.PostgresManager()),
            ],
        ),
        TestDefaultPartition(
            model_name="MonitorCheck",
            name="default",
        ),
        migrations.RunPython(create_partitions, migrations.RunPython.noop),
    ]