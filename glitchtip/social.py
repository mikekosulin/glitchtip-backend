from django.conf import settings
from django.contrib.auth import get_backends
from rest_framework import serializers
from rest_framework.response import Response
from dj_rest_auth.registration.views import SocialConnectView, SocialLoginView
from dj_rest_auth.registration.serializers import (
    SocialLoginSerializer as BaseSocialLoginSerializer,
)
from django_rest_mfa.helpers import has_mfa
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.auth_backends import AuthenticationBackend
from allauth.socialaccount.providers.gitlab.views import GitLabOAuth2Adapter
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.microsoft.views import MicrosoftGraphOAuth2Adapter
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client


DOMAIN = settings.GLITCHTIP_URL.geturl()


class MFAAccountAdapter(DefaultAccountAdapter):
    """
    If user requires MFA, do not actually log in
    """

    def login(self, request, user):
        """Extend to check for MFA status, backend hack is copied from super method"""
        if not hasattr(user, "backend"):
            backends = get_backends()
            backend = None
            for b in backends:
                if isinstance(b, AuthenticationBackend):
                    # prefer our own backend
                    backend = b
                    break
                elif not backend and hasattr(b, "get_user"):
                    # Pick the first valid one
                    backend = b
            backend_path = ".".join([backend.__module__, backend.__class__.__name__])
            user.backend = backend_path
        if has_mfa(request, user):
            user.mfa = True  # Store for later, to avoid multiple DB checks
        else:
            super().login(request, user)

    def get_login_redirect_url(self, request):
        """Ignore login redirect when not logged in"""
        try:
            return super().get_login_redirect_url(request)
        except AssertionError:
            pass


class SocialLoginSerializer(BaseSocialLoginSerializer):
    tags = serializers.CharField(
        allow_blank=True, required=False, allow_null=True, write_only=True
    )


class MFASocialLoginView(SocialLoginView):
    serializer_class = SocialLoginSerializer

    def process_login(self):
        tags = self.serializer.validated_data.get("tags")
        if tags and self.user.analytics is None:
            self.user.set_register_analytics_tags(tags)
            self.user.save(update_fields=["analytics"])

        if not getattr(self.user, "mfa", False):
            super().process_login()

    def get_response(self):
        if getattr(self.user, "mfa", False):
            user_key_types = (
                self.user.userkey_set.all()
                .values_list("key_type", flat=True)
                .distinct()
            )
            return Response({"requires_mfa": True, "valid_auth": user_key_types})
        return super().get_response()


class GitlabConnect(SocialConnectView):
    adapter_class = GitLabOAuth2Adapter


class GitlabLogin(MFASocialLoginView):
    adapter_class = GitLabOAuth2Adapter


class GithubConnect(SocialConnectView):
    adapter_class = GitHubOAuth2Adapter
    client_class = OAuth2Client
    callback_url = DOMAIN + "/auth/github"


class GithubLogin(MFASocialLoginView):
    adapter_class = GitHubOAuth2Adapter
    client_class = OAuth2Client
    callback_url = DOMAIN + "/auth/github"


class GoogleConnect(SocialConnectView):
    adapter_class = GoogleOAuth2Adapter


class GoogleLogin(MFASocialLoginView):
    adapter_class = GoogleOAuth2Adapter


class MicrosoftConnect(SocialConnectView):
    adapter_class = MicrosoftGraphOAuth2Adapter


class MicrosoftLogin(MFASocialLoginView):
    adapter_class = MicrosoftGraphOAuth2Adapter
