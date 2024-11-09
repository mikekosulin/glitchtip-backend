import logging
import typing
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Union
from urllib.parse import parse_qs, urlparse

from django.utils.timezone import now
from ninja import Field
from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    JsonValue,
    RootModel,
    ValidationError,
    WrapValidator,
    field_validator,
    model_validator,
)

from apps.issue_events.constants import IssueEventType

from ..shared.schema.base import LaxIngestSchema
from ..shared.schema.contexts import Contexts
from ..shared.schema.event import (
    BaseIssueEvent,
    BaseRequest,
    EventBreadcrumb,
    ListKeyValue,
)
from ..shared.schema.user import EventUser
from ..shared.schema.utils import invalid_to_none

logger = logging.getLogger(__name__)


CoercedStr = Annotated[
    str, BeforeValidator(lambda v: str(v) if isinstance(v, (bool, list)) else v)
]
"""
Coerced Str that will coerce bool/list to str when found
"""


def coerce_list(v: Any) -> Any:
    """Wrap non-list dict into list: {"a": 1} to [{"a": 1}]"""
    return v if not isinstance(v, dict) else [v]


class Signal(LaxIngestSchema):
    number: int
    code: int | None
    name: str | None
    code_name: str | None


class MachException(LaxIngestSchema):
    number: int
    code: int
    subcode: int
    name: str | None


class NSError(LaxIngestSchema):
    code: int
    domain: str


class Errno(LaxIngestSchema):
    number: int
    name: str | None


class MechanismMeta(LaxIngestSchema):
    signal: Signal | None = None
    match_exception: MachException | None = None
    ns_error: NSError | None = None
    errno: Errno | None = None


class ExceptionMechanism(LaxIngestSchema):
    type: str
    description: str | None = None
    help_link: str | None = None
    handled: bool | None = None
    synthetic: bool | None = None
    meta: dict | None = None
    data: dict | None = None


class StackTraceFrame(LaxIngestSchema):
    filename: str | None = None
    function: str | None = None
    raw_function: str | None = None
    module: str | None = None
    lineno: int | None = None
    colno: int | None = None
    abs_path: str | None = None
    context_line: str | None = None
    pre_context: list[str | None] | None = None
    post_context: list[str | None] | None = None
    source_link: str | None = None
    in_app: bool | None = None
    stack_start: bool | None = None
    vars: dict[str, Union[str, dict, list]] | None = None
    instruction_addr: str | None = None
    addr_mode: str | None = None
    symbol_addr: str | None = None
    image_addr: str | None = None
    package: str | None = None
    platform: str | None = None

    def is_url(self, filename: str) -> bool:
        return filename.startswith(("file:", "http:", "https:", "applewebdata:"))

    @model_validator(mode="after")
    def normalize_files(self):
        if not self.abs_path and self.filename:
            self.abs_path = self.filename
        if self.filename and self.is_url(self.filename):
            self.filename = urlparse(self.filename).path
        return self

    @field_validator("pre_context", "post_context")
    @classmethod
    def replace_null(cls, context: list[str | None]) -> list[str | None] | None:
        if context:
            return [line if line else "" for line in context]
        return None


class StackTrace(LaxIngestSchema):
    frames: list[StackTraceFrame]
    registers: dict[str, str] | None = None


class EventException(LaxIngestSchema):
    type: str | None = None
    value: Annotated[str | None, WrapValidator(invalid_to_none)] = None
    module: str | None = None
    thread_id: str | None = None
    mechanism: Annotated[ExceptionMechanism | None, WrapValidator(invalid_to_none)] = (
        None
    )
    stacktrace: Annotated[StackTrace | None, WrapValidator(invalid_to_none)] = None

    @model_validator(mode="after")
    def check_type_value(self):
        if self.type is None and self.value is None:
            return None
        return self


class ValueEventException(LaxIngestSchema):
    values: list[EventException]

    @field_validator("values")
    @classmethod
    def strip_null(cls, v: list[EventException]) -> list[EventException]:
        return [e for e in v if e is not None]


class EventMessage(LaxIngestSchema):
    formatted: str = Field(max_length=8192, default="")
    message: str | None = None
    params: list[CoercedStr] | dict[str, str] | None = None

    @model_validator(mode="after")
    def set_formatted(self) -> "EventMessage":
        """
        When the EventMessage formatted string is not set,
        attempt to set it based on message and params interpolation
        """
        if not self.formatted and self.message:
            params = self.params
            if isinstance(params, list) and params:
                self.formatted = self.message % tuple(params)
            elif isinstance(params, dict):
                self.formatted = self.message.format(**params)
        return self


class EventTemplate(LaxIngestSchema):
    lineno: int
    abs_path: str | None = None
    filename: str
    context_line: str
    pre_context: list[str] | None = None
    post_context: list[str] | None = None


# Important, for some reason using Schema will cause the DebugImage union not to work
class SourceMapImage(BaseModel):
    type: Literal["sourcemap"]
    code_file: str
    debug_id: uuid.UUID


# Important, for some reason using Schema will cause the DebugImage union not to work
class OtherDebugImage(BaseModel):
    type: str


DebugImage = Annotated[SourceMapImage, Field(discriminator="type")] | OtherDebugImage


class DebugMeta(LaxIngestSchema):
    images: list[DebugImage]


class ValueEventBreadcrumb(LaxIngestSchema):
    values: list[EventBreadcrumb]


class ClientSDKPackage(LaxIngestSchema):
    name: str | None = None
    version: str | None = None


class ClientSDKInfo(LaxIngestSchema):
    integrations: list[str | None] | None = None
    name: str | None
    packages: list[ClientSDKPackage] | None = None
    version: str | None

    @field_validator("packages", mode="before")
    def name_must_contain_space(cls, v: Any) -> Any:
        return coerce_list(v)


class RequestHeaders(LaxIngestSchema):
    content_type: str | None


class RequestEnv(LaxIngestSchema):
    remote_addr: str | None


QueryString = str | ListKeyValue | dict[str, str | dict[str, Any] | None]
"""Raw URL querystring, list, or dict"""
KeyValueFormat = Union[list[list[str | None]], dict[str, CoercedStr | None]]
"""
key-values in list or dict format. Example {browser: firefox} or [[browser, firefox]]
"""


class IngestRequest(BaseRequest):
    headers: KeyValueFormat | None = None
    query_string: QueryString | None = None

    @field_validator("headers", mode="before")
    @classmethod
    def fix_non_standard_headers(cls, v):
        """
        Fix non-documented format used by PHP Sentry Client
        Convert {"Foo": ["bar"]} into {"Foo: "bar"}
        """
        if isinstance(v, dict):
            return {
                key: value[0] if isinstance(value, list) else value
                for key, value in v.items()
            }
        return v

    @field_validator("query_string", "headers")
    @classmethod
    def prefer_list_key_value(
        cls, v: Union[QueryString, KeyValueFormat] | None
    ) -> ListKeyValue | None:
        """Store all querystring, header formats in a list format"""
        result: ListKeyValue | None = None
        if isinstance(v, str) and v:  # It must be a raw querystring, parse it
            qs = parse_qs(v)
            result = [[key, value] for key, values in qs.items() for value in values]
        elif isinstance(v, dict):  # Convert dict to list
            result = [[key, value] for key, value in v.items()]
        elif isinstance(v, list):  # Normalize list (throw out any weird data)
            result = [item[:2] for item in v if len(item) >= 2]

        if result:
            # Remove empty and any key called "Cookie" which could be sensitive data
            entry_to_remove = ["Cookie", ""]
            return sorted(
                [entry for entry in result if entry != entry_to_remove],
                key=lambda x: (x[0], x[1]),
            )
        return result


class IngestIssueEvent(BaseIssueEvent):
    timestamp: datetime = Field(default_factory=now)
    level: str | None = "error"
    logentry: EventMessage | None = None
    logger: str | None = None
    transaction: str | None = Field(
        validation_alias=AliasChoices("transaction", "culprit"), default=None
    )
    server_name: str | None = None
    release: str | None = None
    dist: str | None = None
    tags: KeyValueFormat | None = None
    environment: str | None = None
    modules: dict[str, str | None] | None = None
    extra: dict[str, Any] | None = None
    fingerprint: list[Union[str, None]] | None = None
    errors: list[Any] | None = None

    exception: Union[list[EventException], ValueEventException] | None = None
    message: Union[str, EventMessage] | None = None
    template: EventTemplate | None = None

    breadcrumbs: Union[list[EventBreadcrumb], ValueEventBreadcrumb] | None = None
    sdk: ClientSDKInfo | None = None
    request: IngestRequest | None = None
    contexts: Contexts | None = None
    user: EventUser | None = None
    debug_meta: DebugMeta | None = None

    @field_validator("tags")
    @classmethod
    def prefer_dict(cls, v: KeyValueFormat | None) -> dict[str, str | None] | None:
        if isinstance(v, list):
            return {key: value for key, value in v if key is not None}
        return v


class EventIngestSchema(IngestIssueEvent):
    event_id: uuid.UUID


class TransactionEventSchema(LaxIngestSchema):
    type: Literal["transaction"] = "transaction"
    contexts: JsonValue
    measurements: JsonValue | None = None
    start_timestamp: datetime
    timestamp: datetime
    transaction: str

    # # SentrySDKEventSerializer
    breadcrumbs: JsonValue | None = None
    fingerprint: list[str] | None = None
    tags: KeyValueFormat | None = None
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    extra: JsonValue | None = None
    request: IngestRequest | None = None
    server_name: str | None = None
    sdk: ClientSDKInfo | None = None
    platform: str | None
    release: str | None = None
    environment: str | None = None
    _meta: JsonValue | None


class EnvelopeHeaderSchema(LaxIngestSchema):
    event_id: uuid.UUID | None = None
    dsn: str | None = None
    sdk: ClientSDKInfo | None = None
    sent_at: datetime = Field(default_factory=now)


SupportedItemType = Literal["transaction", "event"]
IgnoredItemType = Literal[
    "session", "sessions", "client_report", "attachment", "user_report", "check_in"
]
SUPPORTED_ITEMS = typing.get_args(SupportedItemType)


class ItemHeaderSchema(LaxIngestSchema):
    content_type: str | None = None
    type: Union[SupportedItemType, IgnoredItemType]
    length: int | None = None


class EnvelopeSchema(RootModel[list[dict[str, Any]]]):
    root: list[dict[str, Any]]
    _header: EnvelopeHeaderSchema
    _items: list[
        tuple[ItemHeaderSchema, IngestIssueEvent | TransactionEventSchema]
    ] = []

    @model_validator(mode="after")
    def validate_envelope(self) -> "EnvelopeSchema":
        data = self.root
        try:
            header = data.pop(0)
        except IndexError:
            raise ValidationError([{"message": "Envelope is empty"}])
        self._header = EnvelopeHeaderSchema(**header)

        while len(data) >= 2:
            item_header_data = data.pop(0)
            if item_header_data.get("type", None) not in SUPPORTED_ITEMS:
                continue
            item_header = ItemHeaderSchema(**item_header_data)
            if item_header.type == "event":
                try:
                    item = IngestIssueEvent(**data.pop(0))
                except ValidationError as err:
                    logger.warning("Envelope Event item invalid", exc_info=True)
                    raise err
                self._items.append((item_header, item))
            elif item_header.type == "transaction":
                item = TransactionEventSchema(**data.pop(0))
                self._items.append((item_header, item))

        return self


class CSPReportSchema(LaxIngestSchema):
    """
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy-Report-Only#violation_report_syntax
    """

    blocked_uri: str = Field(alias="blocked-uri")
    disposition: Literal["enforce", "report"] = Field(alias="disposition")
    document_uri: str = Field(alias="document-uri")
    effective_directive: str = Field(alias="effective-directive")
    original_policy: str | None = Field(alias="original-policy")
    script_sample: str | None = Field(alias="script-sample", default=None)
    status_code: int | None = Field(alias="status-code")
    line_number: int | None = None
    column_number: int | None = None


class SecuritySchema(LaxIngestSchema):
    csp_report: CSPReportSchema = Field(alias="csp-report")


## Normalized Interchange Issue Events


class IssueEventSchema(IngestIssueEvent):
    """
    Event storage and interchange format
    Used in json view and celery interchange
    Don't use this for api intake
    """

    type: Literal[IssueEventType.DEFAULT] = IssueEventType.DEFAULT


class ErrorIssueEventSchema(IngestIssueEvent):
    type: Literal[IssueEventType.ERROR] = IssueEventType.ERROR


class CSPIssueEventSchema(IngestIssueEvent):
    type: Literal[IssueEventType.CSP] = IssueEventType.CSP
    csp: CSPReportSchema


class InterchangeEvent(LaxIngestSchema):
    """Normalized wrapper around issue event. Event should not contain repeat information."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    project_id: int
    organization_id: int
    received: datetime = Field(default_factory=now)
    payload: (
        IssueEventSchema
        | ErrorIssueEventSchema
        | CSPIssueEventSchema
        | TransactionEventSchema
    ) = Field(discriminator="type")


class InterchangeIssueEvent(InterchangeEvent):
    payload: (
        IssueEventSchema
        | ErrorIssueEventSchema
        | CSPIssueEventSchema
        | TransactionEventSchema
    ) = Field(discriminator="type")


class InterchangeTransactionEvent(InterchangeEvent):
    payload: TransactionEventSchema
