from urllib.parse import urlparse
from django.utils.encoding import force_text
from rest_framework import serializers
from sentry.eventtypes.error import ErrorEvent
from issues.models import EventType, Event, Issue
from sentry.culprit import generate_culprit


class StoreDefaultSerializer(serializers.Serializer):
    type = EventType.DEFAULT
    breadcrumbs = serializers.JSONField()
    contexts = serializers.JSONField(required=False)
    event_id = serializers.UUIDField()
    extra = serializers.JSONField(required=False)
    level = serializers.CharField()
    message = serializers.CharField(required=False)
    platform = serializers.CharField()
    release = serializers.CharField(required=False)
    sdk = serializers.JSONField()
    timestamp = serializers.DateTimeField(required=False)
    modules = serializers.JSONField(required=False)

    def create(self, project, data):
        error = ErrorEvent()


class StoreErrorSerializer(StoreDefaultSerializer):
    type = EventType.ERROR
    exception = serializers.JSONField(required=False)
    request = serializers.JSONField(required=False)
    transaction = serializers.CharField(required=False)
    timestamp = serializers.DateTimeField(required=False)

    def create(self, project, data):
        error = ErrorEvent()
        metadata = error.get_metadata(data)
        title = error.get_title(metadata)
        issue, _ = Issue.objects.get_or_create(
            title=title,
            culprit=error.get_location(metadata),
            project=project,
            type=EventType.ERROR,
            defaults={"metadata": metadata},
        )

        # level_tag, _ = EventTag.objects.get_or_create(key="level", value=data["level"])
        # release tag
        entries = []
        breadcrumbs = data.get("breadcrumbs")
        if breadcrumbs:
            entries.append({"type": "breadcrumbs", "data": {"values": breadcrumbs}})

        params = {
            "event_id": data["event_id"],
            "issue": issue,
            "timestamp": data.get("timestamp"),
            "data": {
                "contexts": data.get("contexts"),
                "culprit": self.get_culprit(data),
                "exception": data.get("exception"),
                "metadata": metadata,
                "packages": data.get("modules"),
                "platform": data["platform"],
                "sdk": data["sdk"],
                "title": title,
            },
        }
        # if data.get("context"):
        #     params["context"] = data["extra"]

        event = Event.objects.create(**params)
        return event
        # event.tags.add(level_tag)

    def get_culprit(self, data):
        """Helper to calculate the default culprit"""
        return force_text(
            data.get("culprit")
            or data.get("transaction")
            or generate_culprit(data)
            or ""
        )


class StoreCSPReportSerializer(serializers.Serializer):
    """ Very different format from others """

    type = EventType.CSP

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This is done to support the hyphen
        self.fields.update({"csp-report": serializers.JSONField()})

    def create(self, project, data):
        csp = data["csp-report"]
        title = self.get_title(csp)
        culprit = ""
        metadata = {}
        issue, _ = Issue.objects.get_or_create(
            title=title,
            culprit=culprit,
            project=project,
            type=EventType.CSP,
            defaults={"metadata": metadata},
        )
        params = {
            "issue": issue,
            "data": {},
        }
        return Event.objects.create(**params)

    def get_effective_directive(self, data):
        """
        Some browers return effective-directive and others don't.
        Infer missing ones from violated directive
        """
        if "effective-directive" in data:
            return data["effective-directive"]
        first_violation = data["violated-directive"].split()[0]
        return first_violation

    def get_title(self, data):
        # "Blocked 'style' from 'example.com'"
        effective_directive = self.get_effective_directive(data)
        humanized_directive = effective_directive.replace("-src", "")
        url = data["blocked-uri"]
        host = urlparse(url).netloc
        return f"Blocked '{humanized_directive}' from '{host}'"

    def get_culprit(self, data):
        return ""
