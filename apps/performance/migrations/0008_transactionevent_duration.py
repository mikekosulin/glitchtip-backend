# Generated by Django 4.0.4 on 2022-04-27 19:02

import datetime
from django.db import migrations, models
from django.db.models import F


def forwards_func(apps, schema_editor):
    TransactionEvent = apps.get_model("performance", "TransactionEvent")
    TransactionEvent.objects.update(duration=F("timestamp") - F("start_timestamp"))


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        (
            "performance",
            "0007_transactionevent_tags_transactiongroup_search_vector_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="transactionevent",
            name="duration",
            field=models.DurationField(db_index=True, default=datetime.timedelta(0)),
            preserve_default=False,
        ),
        migrations.RunPython(forwards_func, reverse_func),
    ]