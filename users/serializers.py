from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from dj_rest_auth.serializers import UserDetailsSerializer as BaseUserDetailsSerializer
from dj_rest_auth.registration.serializers import SocialAccountSerializer
from allauth.account.adapter import get_adapter
from allauth.account import app_settings
from allauth.account.utils import filter_users_by_email
from allauth.account.models import EmailAddress
from .models import User


class EmailSerializer(serializers.ModelSerializer):
    isPrimary = serializers.BooleanField(source="primary", read_only=True)
    email = serializers.EmailField()  # Remove default unique validation
    isVerified = serializers.BooleanField(source="verified", read_only=True)

    class Meta:
        model = EmailAddress
        fields = ("isPrimary", "email", "isVerified")

    def clean_email(self):
        """ Validate email as done in allauth.account.forms.AddEmailForm """
        value = self.cleaned_data["email"]
        value = get_adapter().clean_email(value)
        errors = {
            "this_account": _(
                "This e-mail address is already associated" " with this account."
            ),
            "different_account": _(
                "This e-mail address is already associated" " with another account."
            ),
        }
        users = filter_users_by_email(value)
        on_this_account = [u for u in users if u.pk == self.user.pk]
        on_diff_account = [u for u in users if u.pk != self.user.pk]

        if on_this_account:
            raise serializers.ValidationError(errors["this_account"])
        if on_diff_account and app_settings.UNIQUE_EMAIL:
            raise serializers.ValidationError(errors["different_account"])
        return value

    def validate(self, data):
        self.user = self.context["request"].user
        self.cleaned_data = data
        data["email"] = self.clean_email()
        return data

    def create(self, data):
        return EmailAddress.objects.add_email(
            self.context["request"], self.user, data["email"], confirm=True
        )


class UserSerializer(serializers.ModelSerializer):
    lastLogin = serializers.DateTimeField(source="last_login", read_only=True)
    isSuperuser = serializers.BooleanField(source="is_superuser")
    identities = SocialAccountSerializer(
        source="socialaccount_set", many=True, read_only=True
    )
    isActive = serializers.BooleanField(source="is_active")
    dateJoined = serializers.DateTimeField(source="created", read_only=True)
    hasPasswordAuth = serializers.BooleanField(
        source="has_usable_password", read_only=True
    )

    class Meta:
        model = User
        fields = (
            "lastLogin",
            "isSuperuser",
            "identities",
            "id",
            "isActive",
            "dateJoined",
            "hasPasswordAuth",
            "email",
        )


class UserNotificationsSerializer(serializers.ModelSerializer):
    subscribeByDefault = serializers.BooleanField(source="subscribe_by_default")

    class Meta:
        model = User
        fields = ("subscribeByDefault",)


class UserDetailsSerializer(BaseUserDetailsSerializer):
    """ Extended UserDetailsSerializer with social account set data """

    socialaccount_set = SocialAccountSerializer(many=True, read_only=True)

    class Meta(BaseUserDetailsSerializer.Meta):
        fields = (
            "pk",
            "email",
            "first_name",
            "last_name",
            "socialaccount_set",
        )
        read_only_fields = ("email",)
