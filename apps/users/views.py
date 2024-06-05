from allauth.account.models import EmailAddress
from dj_rest_auth.registration.views import (
    SocialAccountDisconnectView as BaseSocialAccountDisconnectView,
)
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.projects.models import UserProjectAlert

from .models import User
from .serializers import (
    ConfirmEmailAddressSerializer,
    CurrentUserSerializer,
    EmailAddressSerializer,
    UserNotificationsSerializer,
    UserSerializer,
)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        organization_slug = self.kwargs.get("organization_slug")
        if organization_slug:
            queryset = queryset.filter(
                organizations_ext_organization__slug=organization_slug,
                organizations_ext_organization__users=self.request.user,
            )
        else:
            queryset = queryset.filter(id=self.request.user.id)
        return queryset

    def get_object(self):
        if self.kwargs.get("pk") == "me":
            return self.request.user
        return super().get_object()

    def get_serializer_class(self):
        if self.kwargs.get("pk") == "me":
            return CurrentUserSerializer
        return super().get_serializer_class()

    @action(detail=True, methods=["get", "post", "put"])
    def notifications(self, request, pk=None):
        user = self.get_object()

        if request.method == "GET":
            serializer = UserNotificationsSerializer(user)
            return Response(serializer.data)

        serializer = UserNotificationsSerializer(user, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=True, methods=["get", "post", "put"], url_path="notifications/alerts"
    )
    def alerts(self, request, pk=None):
        """
        Returns dictionary of project_id: status. Now project_id status means it's "default"

        To update, submit `{project_id: status}` where status is -1 (default), 0, or 1
        """
        user = self.get_object()
        alerts = user.userprojectalert_set.all()

        if request.method == "GET":
            data = {}
            for alert in alerts:
                data[alert.project_id] = alert.status
            return Response(data)

        data = request.data
        try:
            items = [x for x in data.items()]
        except AttributeError as err:
            raise exceptions.ValidationError(
                "Invalid alert format, expected dictionary"
            ) from err
        if len(data) != 1:
            raise exceptions.ValidationError("Invalid alert format, expected one value")
        project_id, alert_status = items[0]
        if alert_status not in [1, 0, -1]:
            raise exceptions.ValidationError("Invalid status, must be -1, 0, or 1")
        alert = alerts.filter(project_id=project_id).first()
        if alert and alert_status == -1:
            alert.delete()
        else:
            UserProjectAlert.objects.update_or_create(
                user=user, project_id=project_id, defaults={"status": alert_status}
            )
        return Response(status=204)


class EmailAddressViewSet(
    viewsets.GenericViewSet,
):
    queryset = EmailAddress.objects.all()
    serializer_class = EmailAddressSerializer
    pagination_class = None

    def get_user(self, user_pk):
        if user_pk == "me":
            return self.request.user
        raise exceptions.ValidationError(
            "Can only change primary email address on own account"
        )

    def get_queryset(self):
        user = self.get_user(self.kwargs.get("user_pk"))
        queryset = super().get_queryset().filter(user=user)
        return queryset

    @action(detail=False, methods=["post"])
    def confirm(self, request, user_pk):
        serializer = ConfirmEmailAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email_address = get_object_or_404(
            self.get_queryset(), email=serializer.validated_data.get("email")
        )
        email_address.send_confirmation(request)
        return Response(status=204)


class SocialAccountDisconnectView(BaseSocialAccountDisconnectView):
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except ValidationError as e:
            raise exceptions.ValidationError(e.message)
