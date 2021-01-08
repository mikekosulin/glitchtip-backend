# Generated by Django 3.0.7 on 2020-06-12 15:20

import django.contrib.postgres.fields.jsonb
import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid
from .sql.triggers import UPDATE_ISSUE_TRIGGER


class Migration(migrations.Migration):

    replaces = [
        ("issues", "0001_initial"),
        ("issues", "0002_auto_20200306_1546"),
        ("issues", "0003_event_search_vector"),
        ("issues", "0004_auto_20200612_0027"),
    ]

    initial = True

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventTag",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=255)),
                ("value", models.CharField(max_length=225)),
            ],
        ),
        migrations.CreateModel(
            name="Issue",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("culprit", models.CharField(blank=True, max_length=1024, null=True)),
                ("has_seen", models.BooleanField(default=False)),
                ("is_public", models.BooleanField(default=False)),
                (
                    "level",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "sample"),
                            (1, "debug"),
                            (2, "info"),
                            (3, "warning"),
                            (4, "error"),
                            (5, "fatal"),
                        ],
                        default=0,
                    ),
                ),
                ("metadata", django.contrib.postgres.fields.jsonb.JSONField()),
                ("title", models.CharField(max_length=255)),
                (
                    "type",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "default"), (1, "error"), (2, "csp")], default=0
                    ),
                ),
                (
                    "status",
                    models.PositiveSmallIntegerField(
                        choices=[(0, "unresolved"), (1, "resolved"), (2, "ignored")],
                        default=0,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="projects.Project",
                    ),
                ),
            ],
            options={"unique_together": {("title", "culprit", "project", "type")},},
        ),
        migrations.CreateModel(
            name="Event",
            fields=[
                (
                    "event_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "timestamp",
                    models.DateTimeField(
                        blank=True,
                        help_text="Date created as claimed by client it came from",
                        null=True,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("data", django.contrib.postgres.fields.jsonb.JSONField()),
                (
                    "issue",
                    models.ForeignKey(
                        help_text="Sentry calls this a group",
                        on_delete=django.db.models.deletion.CASCADE,
                        to="issues.Issue",
                    ),
                ),
                (
                    "search_vector",
                    django.contrib.postgres.search.SearchVectorField(
                        editable=False, null=True
                    ),
                ),
            ],
            options={"ordering": ["-created"],},
        ),
        migrations.RemoveField(model_name="event", name="search_vector",),
        migrations.AddField(
            model_name="issue",
            name="count",
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name="issue",
            name="last_seen",
            field=models.DateTimeField(
                auto_now_add=True, default=django.utils.timezone.now
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="issue",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(
                editable=False, null=True
            ),
        ),
        migrations.AddIndex(
            model_name="issue",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["search_vector"], name="search_vector_idx"
            ),
        ),
    ]
