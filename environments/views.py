from rest_framework import viewsets
from .models import Environment, EnvironmentProject
from .serializers import EnvironmentSerializer, EnvironmentProjectSerializer
from .permissions import EnvironmentPermission, EnvironmentProjectPermission


class EnvironmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer
    permission_classes = [EnvironmentPermission]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return self.queryset.none()
        queryset = self.queryset.filter(organization__users=self.request.user)
        organization_slug = self.kwargs.get("organization_slug")
        if organization_slug:
            queryset = queryset.filter(organization__slug=organization_slug)
        return queryset


class EnvironmentProjectViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EnvironmentProject.objects.all()
    serializer_class = EnvironmentProjectSerializer
    permission_classes = [EnvironmentProjectPermission]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return self.queryset.none()
        queryset = self.queryset.filter(
            environment__organization__users=self.request.user
        )
        organization_slug = self.kwargs.get("organization_slug")
        if organization_slug:
            queryset = queryset.filter(
                environment__organization__slug=organization_slug
            )
        project_slug = self.kwargs.get("project_slug")
        if project_slug:
            queryset = queryset.filter(project__slug=project_slug)
        return queryset.select_related("environment")
