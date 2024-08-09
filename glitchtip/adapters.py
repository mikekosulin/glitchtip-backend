from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.authentication import record_authentication
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from apps.users.utils import is_user_registration_open


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return is_user_registration_open()


class CustomDefaultAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return is_user_registration_open()

    def save_user(self, request, user, form, commit=True):
        # Consider a signup a form of authentication
        user = super().save_user(request, user, form, commit)
        if commit:
            record_authentication(request, method="signup")
        return user
