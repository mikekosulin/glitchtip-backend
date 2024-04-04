# Generated by Django 5.0.2 on 2024-03-12 13:44
import os
from datetime import timedelta

from django.db import connection, migrations
from django.db.models import Value
from django.conf import settings
from django.utils.timezone import now
from django.contrib.postgres.search import SearchVector

from apps.issue_events.constants import IssueEventType


MIGRATION_LIMIT = os.getenv("ISSUE_EVENT_MIGRATION_LIMIT", 50000)
MIGRATION_LIMIT = int(MIGRATION_LIMIT)


def reformat_data(data):
    if "exception" in data and data["exception"]:
        if "values" in data["exception"]:
            data["exception"] = data["exception"]["values"]
    if "breadcrumbs" in data and data["breadcrumbs"]:
        if "values" in data["breadcrumbs"]:
            data["breadcrumbs"] = data["breadcrumbs"]["values"]
    return data


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def migrate_issue_events(apps, schema_editor):
    if settings.TESTING:
        return
    today = now()
    days_ago = timedelta(days=settings.GLITCHTIP_MAX_EVENT_LIFE_DAYS + 1)
    with connection.cursor() as cursor:
        for single_date in daterange(today - days_ago, today):
            str_date = single_date.strftime("%Y_%b_%d").lower()
            from_date = single_date.date()  # strftime("%Y-%m-%d")
            to_date = (single_date + timedelta(days=1)).date()  # strftime("%Y-%m-%d")
            table_name = "issue_events_issueevent_" + str_date
            sql = f"""CREATE TABLE IF NOT EXISTS {table_name} PARTITION OF issue_events_issueevent
FOR VALUES FROM (%s) TO (%s);
COMMENT ON TABLE {table_name} IS 'psqlextra_auto_partitioned';
"""
            cursor.execute(sql, [from_date, to_date])

    OldIssue = apps.get_model("issues", "Issue")
    Event = apps.get_model("events", "Event")
    Issue = apps.get_model("issue_events", "Issue")
    IssueEvent = apps.get_model("issue_events", "IssueEvent")

    oldest_event = Event.objects.order_by("-created")[
        MIGRATION_LIMIT : MIGRATION_LIMIT + 1
    ].first()
    start_migration_date = oldest_event.created if oldest_event else None

    old_issues = OldIssue.objects.all().defer("search_vector", "tags")
    if start_migration_date:
        old_issues = old_issues.filter(last_seen__gt=start_migration_date)

    for old_issue in old_issues:
        issue = Issue.objects.create(
            culprit=old_issue.culprit[:1024],
            level=old_issue.level,
            metadata=old_issue.metadata,
            project=old_issue.project,
            title=old_issue.title,
            type=old_issue.type,
            status=old_issue.status,
            short_id=old_issue.short_id,
            search_vector=SearchVector(Value(old_issue.title)),
            count=old_issue.count,
            last_seen=old_issue.last_seen,
        )
        events = old_issue.event_set.order_by("-created")
        if start_migration_date:
            events = events.filter(created__gt=start_migration_date)
        IssueEvent.objects.bulk_create(
            [
                IssueEvent(
                    id=event.event_id,
                    type=IssueEventType.from_string(event.data.get("type", "default")),
                    timestamp=event.timestamp if event.timestamp else event.created,
                    received=event.created,
                    title=event.data.get("title"),
                    transaction=event.data.get("culprit")[:200],
                    level=event.level,
                    data=reformat_data(event.data),
                    tags=event.tags,
                    issue=issue,
                )
                for event in events[:1000]
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_squashed_0003_auto_20210219_1951"),
        ("issues", "0013_alter_comment_options_alter_issue_unique_together_and_more"),
        ("issue_events", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrate_issue_events, migrations.RunPython.noop),
    ]
