# Generated by Django 4.2 on 2023-04-28 00:27

import datetime
import django.core.validators
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("uptime", "0005_monitor_timeout"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="monitorcheck",
            options={"ordering": ("-start_check",)},
        ),
        migrations.RemoveIndex(
            model_name="monitorcheck",
            name="uptime_moni_start_c_6434f7_idx",
        ),
        migrations.RemoveField(
            model_name="monitorcheck",
            name="created",
        ),
        migrations.AlterField(
            model_name="monitor",
            name="created",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="monitor",
            name="interval",
            field=models.DurationField(
                default=datetime.timedelta(seconds=60),
                validators=[
                    django.core.validators.MaxValueValidator(datetime.timedelta(days=1))
                ],
            ),
        ),
        migrations.AlterField(
            model_name="monitor",
            name="timeout",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Blank implies default value of 20",
                null=True,
                validators=[
                    django.core.validators.MaxValueValidator(60),
                    django.core.validators.MinValueValidator(1),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="monitorcheck",
            name="start_check",
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                help_text="Time when the start of this check was performed",
            ),
        ),
        migrations.AddIndex(
            model_name="monitor",
            index=models.Index(
                fields=["-created"], name="uptime_moni_created_c41912_idx"
            ),
        ),
    ]