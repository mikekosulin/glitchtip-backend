# Generated by Django 3.2.8 on 2021-10-09 23:02

import collections
from django.db import migrations, models
from .sql.triggers import UPDATE_ISSUE_TRIGGER


def forwards_func(apps, schema_editor):
    Issue = apps.get_model("issues", "Issue")
    for issue in Issue.objects.all()[:5000]:
        tags = (
            issue.event_set.all()
            .order_by("tags")
            .values_list("tags", flat=True)
            .distinct()
        )
        super_dict = collections.defaultdict(set)
        for tag in tags:
            for key, value in tag.items():
                super_dict[key].add(value)
        issue.tags = {k: list(v) for k, v in super_dict.items()}
        issue.save(update_fields=["tags"])


def noop(*args, **kargs):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0004_alter_issue_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="issue", name="tags", field=models.JSONField(default=dict),
        ),
        migrations.RunSQL(UPDATE_ISSUE_TRIGGER, UPDATE_ISSUE_TRIGGER),
        migrations.RunPython(forwards_func, noop),
    ]
