from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from operator import itemgetter
from typing import Any, Optional, Union
from urllib.parse import urlparse

from django.contrib.postgres.search import SearchVector
from django.db import connection, transaction
from django.db.models import (
    Exists,
    F,
    OuterRef,
    Q,
    QuerySet,
    Value,
)
from django.db.models.functions import Coalesce, Greatest
from django.db.utils import IntegrityError
from ninja import Schema
from user_agents import parse

from apps.alerts.models import Notification
from apps.difs.models import DebugInformationFile
from apps.difs.tasks import event_difs_resolve_stacktrace
from apps.environments.models import Environment, EnvironmentProject
from apps.issue_events.constants import EventStatus, LogLevel
from apps.issue_events.models import (
    Issue,
    IssueEvent,
    IssueEventType,
    IssueHash,
    TagKey,
    TagValue,
)
from apps.performance.models import TransactionEvent, TransactionGroup
from apps.projects.models import Project
from apps.releases.models import Release
from sentry.culprit import generate_culprit
from sentry.eventtypes.error import ErrorEvent
from sentry.utils.strings import truncatechars

from ..shared.schema.contexts import (
    BrowserContext,
    ContextsSchema,
    DeviceContext,
    OSContext,
)
from .javascript_event_processor import JavascriptEventProcessor
from .model_functions import PipeConcat
from .schema import (
    ErrorIssueEventSchema,
    IngestIssueEvent,
    InterchangeIssueEvent,
    InterchangeTransactionEvent,
)
from .utils import generate_hash, transform_parameterized_message


@dataclass
class ProcessingEvent:
    event: InterchangeIssueEvent
    issue_hash: str
    title: str
    transaction: str
    metadata: dict[str, Any]
    event_data: dict[str, Any]
    event_tags: dict[str, str]
    level: Optional[LogLevel] = None
    issue_id: Optional[int] = None
    issue_created = False
    release_id: Optional[int] = None


@dataclass
class IssueUpdate:
    last_seen: datetime
    search_vector: str
    added_count: int = 1


def get_search_vector(event: ProcessingEvent) -> str:
    return f"{event.title} {event.transaction}"


Replacable = Union[str, dict, list]


def replace(data: Replacable, match: str, repl: str) -> Replacable:
    """A recursive replace function"""
    if isinstance(data, dict):
        return {k: replace(v, match, repl) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace(i, match, repl) for i in data]
    elif isinstance(data, str):
        return data.replace(match, repl)
    return data


def sanitize_bad_postgres_chars(data: str):
    """
    Remove values which are not supported by the postgres string data types
    """
    known_bads = ["\x00"]
    for known_bad in known_bads:
        data = data.replace(known_bad, " ")
    return data


def sanitize_bad_postgres_json(data: Replacable) -> Replacable:
    """
    Remove values which are not supported by the postgres JSONB data type
    """
    known_bads = ["\u0000"]
    for known_bad in known_bads:
        data = replace(data, known_bad, " ")
    return data


def update_issues(processing_events: list[ProcessingEvent]):
    """
    Update any existing issues based on new statistics
    """
    issues_to_update: dict[int, IssueUpdate] = {}
    for processing_event in processing_events:
        if processing_event.issue_created:
            break

        issue_id = processing_event.issue_id
        if issue_id in issues_to_update:
            issues_to_update[issue_id].added_count += 1
            issues_to_update[
                issue_id
            ].search_vector += f" {get_search_vector(processing_event)}"
            if issues_to_update[issue_id].last_seen < processing_event.event.received:
                issues_to_update[issue_id].last_seen = processing_event.event.received
        elif issue_id:
            issues_to_update[issue_id] = IssueUpdate(
                last_seen=processing_event.event.received,
                search_vector=get_search_vector(processing_event),
            )

    for issue_id, value in issues_to_update.items():
        Issue.objects.filter(id=issue_id).update(
            count=F("count") + value.added_count,
            search_vector=PipeConcat(
                F("search_vector"), SearchVector(Value(value.search_vector))
            ),
            last_seen=Greatest(F("last_seen"), value.last_seen),
        )


def devalue(obj: Union[Schema, list]) -> Optional[Union[dict, list]]:
    """
    Convert Schema like {"values": []} into list or dict without unnecessary 'values'
    """
    if isinstance(obj, Schema) and hasattr(obj, "values"):
        return obj.dict(mode="json", exclude_none=True, exclude_defaults=True)["values"]
    elif isinstance(obj, list):
        return [
            x.dict(mode="json", exclude_none=True, exclude_defaults=True) for x in obj
        ]
    return None


def generate_contexts(event: IngestIssueEvent) -> ContextsSchema:
    """
    Add additional contexts if they aren't already set
    """
    contexts = event.contexts if event.contexts else ContextsSchema(root={})

    if request := event.request:
        if isinstance(request.headers, list):
            if ua_string := next(
                (x[1] for x in request.headers if x[0] == "User-Agent"), None
            ):
                user_agent = parse(ua_string)
                if "browser" not in contexts.root:
                    contexts.root["browser"] = BrowserContext(
                        name=user_agent.browser.family,
                        version=user_agent.browser.version_string,
                    )
                if "os" not in contexts.root:
                    contexts.root["os"] = OSContext(
                        name=user_agent.os.family, version=user_agent.os.version_string
                    )
                if "device" not in contexts.root:
                    device = user_agent.device
                    contexts.root["device"] = DeviceContext(
                        family=device.family,
                        model=device.model,
                        brand=device.brand,
                    )
    return contexts


def generate_tags(event: IngestIssueEvent) -> dict[str, str]:
    """Generate key-value tags based on context and other event data"""
    tags: dict[str, Optional[str]] = event.tags if isinstance(event.tags, dict) else {}

    if contexts := event.contexts:
        if browser := contexts.root.get("browser"):
            if isinstance(browser, BrowserContext):
                tags["browser.name"] = browser.name
                tags["browser"] = f"{browser.name} {browser.version}"
        if os := contexts.root.get("os"):
            if isinstance(os, OSContext):
                tags["os.name"] = os.name
        if device := contexts.root.get("device"):
            if isinstance(device, DeviceContext) and device.model:
                tags["device"] = device.model

    if user := event.user:
        if user.id:
            tags["user.id"] = user.id
        if user.email:
            tags["user.email"] = user.email
        if user.username:
            tags["user.username"] = user.username

    if environment := event.environment:
        tags["environment"] = environment
    if release := event.release:
        tags["release"] = release
    if server_name := event.server_name:
        tags["server_name"] = server_name

    # Exclude None values
    return {key: value for key, value in tags.items() if value}


def check_set_issue_id(
    processing_events: list[ProcessingEvent],
    project_id: int,
    issue_hash: str,
    issue_id: int,
):
    """
    It's common to receive two duplicate events at the same time,
    where the issue has never been seen before. This is an optimization
    that checks if there is a known project/hash. If so, we can infer the
    issue_id.
    """
    for event in processing_events:
        if (
            event.issue_id is None
            and event.event.project_id == project_id
            and event.issue_hash == issue_hash
        ):
            event.issue_id = issue_id


def create_environments(
    environment_set: set[tuple[str, int, int]], projects_with_data: QuerySet
):
    """
    Create newly seen environments.
    Functions determines which, if any, environments are present in event data
    but not the database. Optimized to do a much work in python and reduce queries.
    """
    environments_to_create = [
        Environment(name=name, organization_id=organization_id)
        for name, project_id, organization_id in environment_set
        if not next(
            (
                x
                for x in projects_with_data
                if x["environment_name"] == name and x["id"] == project_id
            ),
            None,
        )
    ]

    if environments_to_create:
        Environment.objects.bulk_create(environments_to_create, ignore_conflicts=True)
        query = Q()
        for environment in environments_to_create:
            query |= Q(
                name=environment.name, organization_id=environment.organization_id
            )
        environments = Environment.objects.filter(query)
        environment_projects: list = []
        for environment in environments:
            project_id = next(
                project_id
                for (name, project_id, organization_id) in environment_set
                if environment.name == name
                and environment.organization_id == organization_id
            )
            environment_projects.append(
                EnvironmentProject(project_id=project_id, environment=environment)
            )
        EnvironmentProject.objects.bulk_create(
            environment_projects, ignore_conflicts=True
        )


def get_and_create_releases(
    release_set: set[tuple[str, int, int]], projects_with_data: QuerySet
) -> list[tuple[str, int, int]]:
    """
    Create newly seen releases.
    functions determines which, if any, releases are present in event data
    but not the database. Optimized to do a much work in python and reduce queries.
    Return list of tuples: Release version, project_id, release_id
    """
    releases_to_create = [
        Release(version=release_name, organization_id=organization_id)
        for release_name, project_id, organization_id in release_set
        if not next(
            (
                x
                for x in projects_with_data
                if x["release_name"] == release_name and x["id"] == project_id
            ),
            None,
        )
    ]
    releases: Union[list, QuerySet] = []
    if releases_to_create:
        # Create database records for any release that doesn't exist
        Release.objects.bulk_create(releases_to_create, ignore_conflicts=True)
        query = Q()
        for release in releases_to_create:
            query |= Q(version=release.version, organization_id=release.organization_id)
        releases = Release.objects.filter(query)
        ReleaseProject = Release.projects.through
        release_projects = [
            ReleaseProject(
                release=release,
                project_id=next(
                    project_id
                    for (version, project_id, organization_id) in release_set
                    if release.version == version
                    and release.organization_id == organization_id
                ),
            )
            for release in releases
        ]
        ReleaseProject.objects.bulk_create(release_projects, ignore_conflicts=True)
    return [
        (
            version,
            project_id,
            next(
                (
                    project["release_id"]
                    for project in projects_with_data
                    if project["release_name"] == version
                    and project["id"] == project_id
                ),
                next(
                    (
                        release.id
                        for release in releases
                        if release.version == version
                        and release.organization_id == organization_id
                    ),
                    0,
                ),
            ),
        )
        for version, project_id, organization_id in release_set
    ]


def process_issue_events(ingest_events: list[InterchangeIssueEvent]):
    """
    Accepts a list of events to ingest. Events should be:
    - Few enough to save in a single DB call
    - Permission is already checked, these events are to write to the DB
    - Some invalid events are tolerated (ignored), including duplicate event id

    When there is an error in this function, care should be taken as to when to log,
    error, or ignore. If the SDK sends "weird" data, we want to log that.
    It's better to save a minimal event than to ignore it.
    """

    # Fetch any needed releases, environments, and whether there is a dif file association
    # Get unique release/environment for each project_id
    release_set = {
        (event.payload.release, event.project_id, event.organization_id)
        for event in ingest_events
        if event.payload.release
    }
    environment_set = {
        (event.payload.environment[:255], event.project_id, event.organization_id)
        for event in ingest_events
        if event.payload.environment
    }
    project_set = {project_id for _, project_id, _ in release_set}.union(
        {project_id for _, project_id, _ in environment_set}
    )
    release_version_set = {version for version, _, _ in release_set}
    environment_name_set = {name for name, _, _ in environment_set}

    projects_with_data = (
        Project.objects.filter(id__in=project_set)
        .annotate(
            has_difs=Exists(
                DebugInformationFile.objects.filter(project_id=OuterRef("pk"))
            ),
            release_id=Coalesce("releases__id", Value(None)),
            release_name=Coalesce("releases__version", Value(None)),
            environment_id=Coalesce("environment__id", Value(None)),
            environment_name=Coalesce("environment__name", Value(None)),
        )
        .filter(release_name__in=release_version_set.union({None}))
        .filter(environment_name__in=environment_name_set.union({None}))
        .values(
            "id",
            "has_difs",
            "release_id",
            "release_name",
            "environment_id",
            "environment_name",
        )
    )

    releases = get_and_create_releases(release_set, projects_with_data)
    create_environments(environment_set, projects_with_data)

    # Collected/calculated event data while processing
    processing_events: list[ProcessingEvent] = []
    # Collect Q objects for bulk issue hash lookup
    q_objects = Q()
    for ingest_event in ingest_events:
        event_data: dict[str, Any] = {}
        event = ingest_event.payload
        event.contexts = generate_contexts(event)
        event_tags = generate_tags(event)
        title = ""
        culprit = ""
        metadata: dict[str, Any] = {}

        release_id = next(
            (
                release_id
                for version, project_id, release_id in releases
                if version == event_tags.get("release")
                and ingest_event.project_id == project_id
            ),
            None,
        )
        if event.platform in ("javascript", "node") and release_id:
            JavascriptEventProcessor(release_id, event).transform()
        elif (
            isinstance(event, ErrorIssueEventSchema)
            and event.exception
            and next(
                (
                    project["has_difs"]
                    for project in projects_with_data
                    if project["id"] == ingest_event.project_id
                ),
                False,
            )
        ):
            event_difs_resolve_stacktrace(event, ingest_event.project_id)

        if event.type in [IssueEventType.ERROR, IssueEventType.DEFAULT]:
            sentry_event = ErrorEvent()
            metadata = sentry_event.get_metadata(event.dict())
            if event.type == IssueEventType.ERROR and metadata:
                full_title = sentry_event.get_title(metadata)
            else:
                message = event.message if event.message else event.logentry
                full_title = (
                    transform_parameterized_message(message)
                    if message
                    else "<untitled>"
                )
                culprit = (
                    event.transaction
                    if event.transaction
                    else generate_culprit(event.dict())
                )
            title = truncatechars(full_title)
            culprit = sentry_event.get_location(event.dict())
        elif event.type == IssueEventType.CSP:
            humanized_directive = event.csp.effective_directive.replace("-src", "")
            uri = urlparse(event.csp.blocked_uri).netloc
            full_title = title = f"Blocked '{humanized_directive}' from '{uri}'"
            culprit = event.csp.effective_directive
            event_data["csp"] = event.csp.dict()
        issue_hash = generate_hash(title, culprit, event.type, event.fingerprint)
        if metadata:
            event_data["metadata"] = metadata
        if platform := event.platform:
            event_data["platform"] = platform
        if modules := event.modules:
            event_data["modules"] = modules
        if sdk := event.sdk:
            event_data["sdk"] = sdk.dict(exclude_none=True)
        if request := event.request:
            event_data["request"] = request.dict(exclude_none=True)
        if environment := event.environment:
            event_data["environment"] = environment

        # Message is str
        # Logentry is {"params": etc} Message format
        if logentry := event.logentry:
            event_data["logentry"] = logentry.dict(exclude_none=True)
        elif message := event.message:
            if isinstance(message, str):
                event_data["logentry"] = {"formatted": message}
            else:
                event_data["logentry"] = message.dict(exclude_none=True)
        if message := event.message:
            event_data["message"] = (
                message if isinstance(message, str) else message.formatted
            )
        # When blank, the API will default to the title anyway
        elif title != full_title:
            # If the title is truncated, store the full title
            event_data["message"] = full_title

        if breadcrumbs := event.breadcrumbs:
            event_data["breadcrumbs"] = devalue(breadcrumbs)
        if exception := event.exception:
            event_data["exception"] = devalue(exception)
        if extra := event.extra:
            event_data["extra"] = extra
        if user := event.user:
            event_data["user"] = user.dict(exclude_none=True)
        if contexts := event.contexts:
            event_data["contexts"] = contexts.dict(exclude_none=True)

        processing_events.append(
            ProcessingEvent(
                event=ingest_event,
                issue_hash=issue_hash,
                title=title,
                level=LogLevel.from_string(event.level) if event.level else None,
                transaction=culprit,
                metadata=metadata,
                event_data=event_data,
                event_tags=event_tags,
                release_id=release_id,
            )
        )
        q_objects |= Q(project_id=ingest_event.project_id, value=issue_hash)

    hash_queryset = IssueHash.objects.filter(q_objects).values(
        "value", "project_id", "issue_id", "issue__status"
    )
    issue_events: list[IssueEvent] = []
    issues_to_reopen = []
    for processing_event in processing_events:
        event_type = processing_event.event.payload.type
        project_id = processing_event.event.project_id
        issue_defaults = {
            "type": event_type,
            "title": sanitize_bad_postgres_chars(processing_event.title),
            "metadata": sanitize_bad_postgres_json(processing_event.metadata),
            "first_seen": processing_event.event.received,
            "last_seen": processing_event.event.received,
        }
        if level := processing_event.level:
            issue_defaults["level"] = level
        for hash_obj in hash_queryset:
            if (
                hash_obj["value"].hex == processing_event.issue_hash
                and hash_obj["project_id"] == project_id
            ):
                processing_event.issue_id = hash_obj["issue_id"]
                if hash_obj["issue__status"] == EventStatus.RESOLVED:
                    issues_to_reopen.append(hash_obj["issue_id"])
                break

        if not processing_event.issue_id:
            try:
                with transaction.atomic():
                    issue = Issue.objects.create(
                        project_id=project_id,
                        search_vector=SearchVector(Value(issue_defaults["title"])),
                        **issue_defaults,
                    )
                    new_issue_hash = IssueHash.objects.create(
                        issue=issue,
                        value=processing_event.issue_hash,
                        project_id=project_id,
                    )
                    check_set_issue_id(
                        processing_events,
                        issue.project_id,
                        new_issue_hash.value,
                        issue.id,
                    )
                processing_event.issue_id = issue.id
                processing_event.issue_created = True
            except IntegrityError:
                processing_event.issue_id = IssueHash.objects.get(
                    project_id=project_id, value=processing_event.issue_hash
                ).issue_id
        issue_events.append(
            IssueEvent(
                id=processing_event.event.event_id,
                issue_id=processing_event.issue_id,
                type=event_type,
                level=processing_event.level
                if processing_event.level
                else LogLevel.ERROR,
                timestamp=processing_event.event.payload.timestamp,
                received=processing_event.event.received,
                title=processing_event.title,
                transaction=processing_event.transaction,
                data=sanitize_bad_postgres_json(processing_event.event_data),
                tags=processing_event.event_tags,
                release_id=processing_event.release_id,
            )
        )

    update_issues(processing_events)

    if issues_to_reopen:
        Issue.objects.filter(id__in=issues_to_reopen).update(
            status=EventStatus.UNRESOLVED
        )
        Notification.objects.filter(issues__in=issues_to_reopen).delete()

    # ignore_conflicts because we could have an invalid duplicate event_id, received
    IssueEvent.objects.bulk_create(issue_events, ignore_conflicts=True)

    # Group events by time and project for event count statistics
    data_stats: defaultdict[datetime, defaultdict[int, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for processing_event in processing_events:
        hour_received = processing_event.event.received.replace(
            minute=0, second=0, microsecond=0
        )
        data_stats[hour_received][processing_event.event.project_id] += 1

    update_tags(processing_events)
    update_statistics(data_stats)


def update_statistics(
    project_event_stats: defaultdict[datetime, defaultdict[int, int]],
):
    # Flatten data for a sql param friendly format and sort to mitigate deadlocks
    data = sorted(
        [
            [year, key, value]
            for year, inner_dict in project_event_stats.items()
            for key, value in inner_dict.items()
        ],
        key=itemgetter(0, 1),
    )
    # Django ORM cannot support F functions in a bulk_update
    # psycopg3 does not support execute_values
    # https://github.com/psycopg/psycopg/issues/114
    with connection.cursor() as cursor:
        args_str = ",".join(cursor.mogrify("(%s,%s,%s)", x) for x in data)
        sql = (
            "INSERT INTO projects_issueeventprojecthourlystatistic (date, project_id, count)\n"
            f"VALUES {args_str}\n"
            "ON CONFLICT (project_id, date)\n"
            "DO UPDATE SET count = projects_issueeventprojecthourlystatistic.count + EXCLUDED.count;"
        )
        cursor.execute(sql)


TagStats = defaultdict[
    datetime,
    defaultdict[int, defaultdict[int, defaultdict[int, int]]],
]


def update_tags(processing_events: list[ProcessingEvent]):
    keys = sorted({key for d in processing_events for key in d.event_tags.keys()})
    values = sorted(
        {value for d in processing_events for value in d.event_tags.values()}
    )

    TagKey.objects.bulk_create([TagKey(key=key) for key in keys], ignore_conflicts=True)
    TagValue.objects.bulk_create(
        [TagValue(value=value) for value in values], ignore_conflicts=True
    )
    # Postgres cannot return ids with ignore_conflicts
    tag_keys = {
        tag["key"]: tag["id"] for tag in TagKey.objects.filter(key__in=keys).values()
    }
    tag_values = {
        tag["value"]: tag["id"]
        for tag in TagValue.objects.filter(value__in=values).values()
    }

    tag_stats: TagStats = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    )
    for processing_event in processing_events:
        if processing_event.issue_id is None:
            continue
        # Group by day. More granular allows for a better search
        # Less granular yields better tag filter performance
        minute_received = processing_event.event.received.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for key, value in processing_event.event_tags.items():
            key_id = tag_keys[key]
            value_id = tag_values[value]
            tag_stats[minute_received][processing_event.issue_id][key_id][value_id] += 1

    if not tag_stats:
        return

    # Sort to mitigate deadlocks
    data = sorted(
        [
            [date, issue_id, key_id, value_id, count]
            for date, d1 in tag_stats.items()
            for issue_id, d2 in d1.items()
            for key_id, d3 in d2.items()
            for value_id, count in d3.items()
        ],
        key=itemgetter(0, 1, 2, 3),
    )
    with connection.cursor() as cursor:
        args_str = ",".join(cursor.mogrify("(%s,%s,%s,%s,%s)", x) for x in data)
        sql = (
            "INSERT INTO issue_events_issuetag (date, issue_id, tag_key_id, tag_value_id, count)\n"
            f"VALUES {args_str}\n"
            "ON CONFLICT (issue_id, date, tag_key_id, tag_value_id)\n"
            "DO UPDATE SET count = issue_events_issuetag.count + EXCLUDED.count;"
        )
        cursor.execute(sql)


# Transactions
def process_transaction_events(ingest_events: list[InterchangeTransactionEvent]):
    for ingest_event in ingest_events:
        event = ingest_event.payload
        contexts = event.contexts
        request = event.request
        trace_id = contexts["trace"]["trace_id"]
        op = ""
        if isinstance(contexts, dict):
            trace = contexts.get("trace", {})
            if isinstance(trace, dict):
                op = str(trace.get("op", ""))
        method: str | None = None
        if request:
            method = request.method

        # TODO tags

        group, group_created = TransactionGroup.objects.get_or_create(
            project_id=ingest_event.project_id,
            transaction=event.transaction,
            op=op,
            method=method,
        )

        TransactionEvent.objects.create(
            group=group,
            data={
                "request": request.dict() if request else None,
                "sdk": event.sdk.dict() if event.sdk else None,
                "platform": event.platform,
            },
            trace_id=trace_id,
            event_id=event.event_id,
            timestamp=event.timestamp,
            start_timestamp=event.start_timestamp,
            duration=(event.timestamp - event.start_timestamp).total_seconds() * 1000,
        )
    # def create(self, validated_data):
    #     data = validated_data
    #     contexts = data["contexts"]
    #     project = self.context.get("project")
    #     trace_id = contexts["trace"]["trace_id

    #     tags = []
    #     release = self.set_release(data.get("release"), project)
    #     if project.release_id:
    #         tags.append(("release", release))
    #     environment = self.set_environment(data.get("environment"), project)
    #     if project.environment_id:
    #         tags.append(("environment", environment))

    #     if data.get("tags"):
    #         tags += [(k, v) for k, v in data["tags"].items()]

    #     defaults = {}
    #     defaults["tags"] = {tag[0]: [tag[1]] for tag in tags}

    #     group, group_created = TransactionGroup.objects.get_or_create(
    #         project=self.context.get("project"),
    #         transaction=data["transaction"],
    #         op=contexts["trace"].get("op", ""),
    #         method=data.get("request", {}).get("method"),
    #         defaults=defaults,
    #     )

    #     # Merge tags, only save if necessary
    #     update_group = False
    #     if not group_created:
    #         for tag in tags:
    #             if tag[0] not in group.tags:
    #                 new_tag_value = tag[1]
    #                 # Coerce to List[str]
    #                 if isinstance(new_tag_value, str):
    #                     new_tag_value = [new_tag_value]
    #                 group.tags[tag[0]] = new_tag_value
    #                 update_group = True
    #             elif tag[1] not in group.tags[tag[0]]:
    #                 group.tags[tag[0]].append(tag[1])
    #                 update_group = True
    #     if update_group:
    #         group.save(update_fields=["tags"])

    #     transaction = TransactionEvent.objects.create(
    #         group=group,
    #         data={
    #             "request": data.get("request"),
    #             "sdk": data.get("sdk"),
    #             "platform": data.get("platform"),
    #         },
    #         trace_id=trace_id,
    #         event_id=data["event_id"],
    #         timestamp=data["timestamp"],
    #         start_timestamp=data["start_timestamp"],
    #         duration=(data["timestamp"] - data["start_timestamp"]).total_seconds()
    #         * 1000,
    #         tags={tag[0]: tag[1] for tag in tags},
    #     )

    #     return transaction
