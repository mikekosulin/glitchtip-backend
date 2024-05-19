from typing import Optional

from django.http import Http404, HttpResponse
from django.shortcuts import aget_object_or_404
from ninja import Router
from ninja.errors import ValidationError

from apps.organizations_ext.models import Organization
from apps.projects.models import Project
from glitchtip.api.authentication import AuthHttpRequest
from glitchtip.api.pagination import paginate
from glitchtip.api.permissions import has_permission

from .models import Release
from .schema import ReleaseBase, ReleaseIn, ReleaseSchema, ReleaseUpdate

router = Router()


"""
POST /organizations/{organization_slug}/releases/
POST /organizations/{organization_slug}/releases/{version}/deploys/ (Not implemented)
GET /organizations/{organization_slug}/releases/
GET /organizations/{organization_slug}/releases/{version}/
PUT /organizations/{organization_slug}/releases/{version}/
DELETE /organizations/{organization_slug}/releases/{version}/
GET /projects/{organization_slug}/{project_slug}/releases/ (sentry undocumented)
GET /projects/{organization_slug}/{project_slug}/releases/{version}/ (sentry undocumented)
POST /projects/{organization_slug}/{project_slug}/releases/ (sentry undocumented)
"""


def get_releases_queryset(
    organization_slug: str,
    user_id: int,
    id: Optional[int] = None,
    version: Optional[str] = None,
    project_slug: Optional[str] = None,
):
    qs = Release.objects.filter(
        organization__slug=organization_slug, organization__users=user_id
    )
    if id:
        qs = qs.filter(id=id)
    if version:
        qs = qs.filter(version=version)
    if project_slug:
        qs = qs.filter(projects__slug=project_slug)
    return qs.prefetch_related("projects")


@router.post(
    "/organizations/{slug:organization_slug}/releases/",
    response={201: ReleaseSchema},
    by_alias=True,
)
@has_permission(["project:releases"])
async def create_release(
    request: AuthHttpRequest, organization_slug: str, payload: ReleaseIn
):
    user_id = request.auth.user_id
    organization = await aget_object_or_404(
        Organization, slug=organization_slug, users=user_id
    )
    data = payload.dict()
    projects = [
        project_id
        async for project_id in Project.objects.filter(
            slug__in=data.pop("projects"), organization=organization
        ).values_list("id", flat=True)
    ]
    if not projects:
        raise ValidationError([{"projects": "Require at least one valid project"}])
    release = await Release.objects.acreate(organization=organization, **data)
    await release.projects.aadd(*projects)
    return await get_releases_queryset(organization_slug, user_id, id=release.id).aget()


@router.post(
    "/projects/{slug:organization_slug}/{slug:project_slug}/releases/",
    response={201: ReleaseSchema},
    by_alias=True,
)
@has_permission(["project:releases"])
async def create_project_release(
    request: AuthHttpRequest, organization_slug: str, project_slug, payload: ReleaseBase
):
    user_id = request.auth.user_id
    project = await aget_object_or_404(
        Project.objects.select_related("organization"),
        slug=project_slug,
        organization__slug=organization_slug,
        organization__users=user_id,
    )
    data = payload.dict()
    version = data.pop("version")
    release, _ = await Release.objects.aget_or_create(
        organization=project.organization, version=version, defaults=data
    )
    await release.projects.aadd(project)
    return await get_releases_queryset(organization_slug, user_id, id=release.id).aget()


@router.get(
    "/organizations/{slug:organization_slug}/releases/",
    response=list[ReleaseSchema],
    by_alias=True,
)
@paginate
@has_permission(["project:releases"])
async def list_releases(
    request: AuthHttpRequest, response: HttpResponse, organization_slug: str
):
    return get_releases_queryset(organization_slug, request.auth.user_id)


@router.get(
    "/organizations/{slug:organization_slug}/releases/{slug:version}/",
    response=ReleaseSchema,
    by_alias=True,
)
@has_permission(["project:releases"])
async def get_release(request: AuthHttpRequest, organization_slug: str, version: str):
    return await aget_object_or_404(
        get_releases_queryset(organization_slug, request.auth.user_id, version=version)
    )


@router.put(
    "/organizations/{slug:organization_slug}/releases/{slug:version}/",
    response=ReleaseSchema,
    by_alias=True,
)
@has_permission(["project:releases"])
async def update_release(
    request: AuthHttpRequest,
    organization_slug: str,
    version: str,
    payload: ReleaseUpdate,
):
    user_id = request.auth.user_id
    release = await aget_object_or_404(
        get_releases_queryset(organization_slug, user_id, version=version)
    )
    for attr, value in payload.dict().items():
        setattr(release, attr, value)
    await release.asave()
    return await get_releases_queryset(organization_slug, user_id, id=release.id).aget()


@router.delete(
    "/organizations/{slug:organization_slug}/releases/{slug:version}/",
    response={204: None},
)
@has_permission(["project:releases"])
async def delete_release(
    request: AuthHttpRequest, organization_slug: str, version: str
):
    result, _ = await get_releases_queryset(
        organization_slug, request.auth.user_id, version=version
    ).adelete()
    if not result:
        raise Http404
    return 204, None


@router.get(
    "/projects/{slug:organization_slug}/{slug:project_slug}/releases/",
    response=list[ReleaseSchema],
    by_alias=True,
)
@paginate
@has_permission(["project:releases"])
async def list_project_releases(
    request: AuthHttpRequest,
    response: HttpResponse,
    organization_slug: str,
    project_slug: str,
):
    return get_releases_queryset(
        organization_slug, request.auth.user_id, project_slug=project_slug
    )


@router.get(
    "/projects/{slug:organization_slug}/{slug:project_slug}/releases/{slug:version}/",
    response=ReleaseSchema,
    by_alias=True,
)
@has_permission(["project:releases"])
async def get_project_release(
    request: AuthHttpRequest, organization_slug: str, project_slug: str, version: str
):
    return await aget_object_or_404(
        get_releases_queryset(
            organization_slug,
            request.auth.user_id,
            project_slug=project_slug,
            version=version,
        )
    )
