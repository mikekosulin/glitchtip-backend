# Generated by Django 5.0.2 on 2024-02-14 14:03

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    replaces = [
        ("releases", "0001_initial"),
        ("releases", "0002_auto_20201227_1518"),
        ("releases", "0003_auto_20210509_1658"),
        ("releases", "0004_alter_release_id_alter_releasefile_id_and_more"),
    ]

    initial = True

    dependencies = [
        ("files", "0001_squashed_0007_remove_file_blobs_file_blob"),
        ("organizations_ext", "0001_squashed_0009_organization_scrub_ip_addresses"),
        (
            "projects",
            "0001_squashed_0009_alter_project_id_alter_projectcounter_id_and_more",
        ),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Release",
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
                ("version", models.CharField(max_length=255)),
                (
                    "ref",
                    models.CharField(
                        blank=True,
                        help_text="May be branch or tag name",
                        max_length=255,
                        null=True,
                    ),
                ),
                ("url", models.URLField(blank=True, null=True)),
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("released", models.DateTimeField(blank=True, null=True)),
                ("data", models.JSONField(default=dict)),
                ("commit_count", models.PositiveSmallIntegerField(default=0)),
                ("deploy_count", models.PositiveSmallIntegerField(default=0)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="organizations_ext.organization",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        help_text="Release manager - the person initiating the release",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "projects",
                    models.ManyToManyField(
                        related_name="releases",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "unique_together": {("organization", "version")},
            },
        ),
        migrations.CreateModel(
            name="ReleaseFile",
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
                ("created", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("ident", models.CharField(max_length=40)),
                ("name", models.TextField()),
                (
                    "file",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="files.file"
                    ),
                ),
                (
                    "release",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="releases.release",
                    ),
                ),
            ],
            options={
                "unique_together": {("release", "file"), ("release", "ident")},
            },
        ),
        migrations.AddField(
            model_name="release",
            name="files",
            field=models.ManyToManyField(
                through="releases.ReleaseFile", to="files.file"
            ),
        ),
        migrations.AlterField(
            model_name="release",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.CreateModel(
            name="ReleaseProject",
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
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="projects.project",
                    ),
                ),
                (
                    "release",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="releases.release",
                    ),
                ),
            ],
            options={
                "unique_together": {("project", "release")},
            },
        ),
    ]