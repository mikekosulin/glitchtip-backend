from urllib.parse import urlparse

from django.conf import settings
from django.core.validators import URLValidator
from django.urls import reverse
from ninja import Field, ModelSchema
from ninja.errors import ValidationError
from pydantic import model_validator

from glitchtip.schema import CamelSchema

from .constants import HTTP_MONITOR_TYPES, MonitorType
from .models import Monitor, MonitorCheck, StatusPage


class MonitorCheckSchema(CamelSchema, ModelSchema):
    class Meta:
        model = MonitorCheck
        fields = ["is_up", "start_check", "reason"]


class MonitorCheckResponseTimeSchema(MonitorCheckSchema, ModelSchema):
    """Monitor check with response time. Used in Monitors detail api and monitor checks list"""

    class Meta(MonitorCheckSchema.Meta):
        fields = MonitorCheckSchema.Meta.fields + ["response_time"]


class MonitorIn(CamelSchema, ModelSchema):
    expected_body: str
    expected_status: int | None
    timeout: int | None

    @model_validator(mode="after")
    def validate(self):
        monitor_type = self.monitor_type
        if self.url == "" and monitor_type in HTTP_MONITOR_TYPES + (MonitorType.SSL,):
            raise ValidationError("URL is required for " + monitor_type)

        if monitor_type in HTTP_MONITOR_TYPES:
            URLValidator()(self.url)

        if self.expected_status is None and monitor_type in [
            MonitorType.GET,
            MonitorType.POST,
        ]:
            raise ValidationError("Expected status is required for " + monitor_type)

        if monitor_type == MonitorType.PORT:
            url = self.url.replace("http://", "//", 1)
            if not url.startswith("//"):
                url = "//" + url
            parsed_url = urlparse(url)
            message = "Invalid Port URL, expected hostname and port"
            try:
                if not all([parsed_url.hostname, parsed_url.port]):
                    raise ValidationError(message)
            except ValueError as err:
                raise ValidationError(message) from err
            self.url = f"{parsed_url.hostname}:{parsed_url.port}"

        return self

    class Meta:
        model = Monitor
        fields = [
            "monitor_type",
            "name",
            "url",
            "project",
            "interval",
        ]


class MonitorSchema(MonitorIn, ModelSchema):
    project: int | None = Field(validation_alias="project_id")
    environment: int | None = Field(validation_alias="environment_id")
    is_up: bool | None = Field(validation_alias="latest_is_up")
    last_change: str | None
    heartbeat_endpoint: str | None
    project_name: str | None = None
    env_name: str | None = None
    checks: list[MonitorCheckSchema]
    organization: int = Field(validation_alias="organization_id")

    class Meta(MonitorIn.Meta):
        fields = [
            "id",
            "monitor_type",
            "endpoint_id",
            "created",
            "name",
            "url",
            "expected_status",
            "expected_body",
            "interval",
            "timeout",
        ]

    @staticmethod
    def resolve_last_change(obj):
        if obj.last_change:
            return obj.last_change.isoformat().replace("+00:00", "Z")

    @staticmethod
    def resolve_heartbeat_endpoint(obj):
        if obj.endpoint_id:
            return settings.GLITCHTIP_URL.geturl() + reverse(
                "api:heartbeat_check",
                kwargs={
                    "organization_slug": obj.organization.slug,
                    "endpoint_id": obj.endpoint_id,
                },
            )

    @staticmethod
    def resolve_project_name(obj):
        if obj.project:
            return obj.project.name


class MonitorDetailSchema(MonitorSchema):
    checks: list[MonitorCheckResponseTimeSchema]


class StatusPageIn(CamelSchema, ModelSchema):
    is_public: bool = False

    class Meta:
        model = StatusPage
        fields = ["name", "is_public"]


class StatusPageSchema(StatusPageIn, ModelSchema):
    monitors: list[MonitorSchema]

    class Meta(StatusPageIn.Meta):
        fields = ["name", "slug", "is_public"]
