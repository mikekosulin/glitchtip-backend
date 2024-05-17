from datetime import datetime

from ninja import Field, ModelSchema, Schema

from apps.projects.schema import ProjectSchema
from glitchtip.schema import CamelSchema

from .models import Team


class TeamIn(Schema):
    slug: str


class ProjectTeamSchema(CamelSchema, ModelSchema):
    """TeamSchema but without projects"""

    id: str
    created: datetime = Field(serialization_alias="dateCreated")
    is_member: bool
    member_count: int

    class Meta:
        model = Team
        fields = ["id", "slug"]

    class Config(CamelSchema.Config):
        coerce_numbers_to_str = True


class TeamSchema(ProjectTeamSchema):
    projects: list[ProjectSchema] = []
