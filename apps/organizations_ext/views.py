from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404
from organizations.backends import invitation_backend
from rest_framework import exceptions, permissions, views, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from .invitation_backend import InvitationTokenGenerator
from .models import Organization, OrganizationUser, OrganizationUserRole
from .permissions import OrganizationMemberPermission
from .serializers.serializers import (
    AcceptInviteSerializer,
    OrganizationSerializer,
    OrganizationUserDetailSerializer,
    OrganizationUserProjectsSerializer,
    OrganizationUserSerializer,
    ReinviteSerializer,
)


class OrganizationViewSet(viewsets.GenericViewSet):
    filter_backends = [OrderingFilter]
    ordering = ["name"]
    ordering_fields = ["name"]
    queryset = Organization.objects.none()
    serializer_class = OrganizationSerializer
    lookup_field = "slug"


class OrganizationMemberViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API compatible with undocumented Sentry endpoint `/api/organizations/<slug>/members/`
    """

    queryset = OrganizationUser.objects.all()
    serializer_class = OrganizationUserSerializer
    permission_classes = [OrganizationMemberPermission]

    def get_serializer_class(self):
        if self.action in ["retrieve"]:
            return OrganizationUserDetailSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return self.queryset.none()
        queryset = self.queryset.filter(organization__users=self.request.user)
        organization_slug = self.kwargs.get("organization_slug")
        if organization_slug:
            queryset = queryset.filter(organization__slug=organization_slug)
        team_slug = self.kwargs.get("team_slug")
        if team_slug:
            queryset = queryset.filter(teams__slug=team_slug)
        return queryset.select_related("organization", "user").prefetch_related(
            "user__socialaccount_set", "organization__owner"
        )

    def get_object(self):
        pk = self.kwargs.get("pk")
        if pk == "me":
            obj = get_object_or_404(self.get_queryset(), user=self.request.user)
            self.check_object_permissions(self.request, obj)
            return obj
        return super().get_object()

    def check_permissions(self, request):
        if self.request.user.is_authenticated and self.action in [
            "create",
            "update",
            "partial_update",
            "destroy",
        ]:
            org_slug = self.kwargs.get("organization_slug")
            try:
                user_org_user = (
                    self.request.user.organizations_ext_organizationuser.get(
                        organization__slug=org_slug
                    )
                )
            except ObjectDoesNotExist:
                raise PermissionDenied("Not a member of this organization")
            if user_org_user.role < OrganizationUserRole.MANAGER:
                raise PermissionDenied(
                    "Must be manager or higher to add/remove organization members"
                )
        return super().check_permissions(request)

    def reinvite(self, request):
        """
        Send additional invitation to user
        This works more like a rest action, but is embedded within the update view for compatibility
        """
        instance = self.get_object()
        serializer = ReinviteSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        invitation_backend().send_invitation(instance)
        serializer = self.serializer_class(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def set_owner(self, request, *args, **kwargs):
        """
        Set this team member as the one and only one Organization owner
        Only an existing Owner or user with the "org:admin" scope is able to perform this.
        """
        new_owner = self.get_object()
        organization = new_owner.organization
        user = request.user
        if not (
            organization.is_owner(user)
            or organization.organization_users.filter(
                user=user, role=OrganizationUserRole.OWNER
            ).exists()
        ):
            raise exceptions.PermissionDenied("Only owner may set organization owner.")
        organization.change_owner(new_owner)
        return self.retrieve(request, *args, **kwargs)


class OrganizationUserViewSet(OrganizationMemberViewSet):
    """
    Extension of OrganizationMemberViewSet that adds projects the user has access to

    API compatible with [get-organization-users](https://docs.sentry.io/api/organizations/get-organization-users/)
    """

    serializer_class = OrganizationUserProjectsSerializer


class AcceptInviteView(views.APIView):
    """Accept invite to organization"""

    serializer_class = AcceptInviteSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def validate_token(self, org_user, token):
        if not InvitationTokenGenerator().check_token(org_user, token):
            raise exceptions.PermissionDenied("Invalid invite token")

    def get(self, request, org_user_id=None, token=None):
        org_user = get_object_or_404(OrganizationUser, pk=org_user_id)
        self.validate_token(org_user, token)
        serializer = self.serializer_class(
            {"accept_invite": False, "org_user": org_user}
        )
        return Response(serializer.data)

    def post(self, request, org_user_id=None, token=None):
        org_user = get_object_or_404(OrganizationUser, pk=org_user_id)
        self.validate_token(org_user, token)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["accept_invite"]:
            org_user.accept_invite(request.user)
        serializer = self.serializer_class(
            {
                "accept_invite": serializer.validated_data["accept_invite"],
                "org_user": org_user,
            }
        )
        return Response(serializer.data)
