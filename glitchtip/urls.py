from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView
from django_rest_mfa.rest_auth_helpers.views import MFALoginView
from organizations.backends import invitation_backend
from rest_framework_nested import routers

from apps.organizations_ext.urls import router as organizationsRouter
from apps.projects.urls import router as projectsRouter
from apps.users.urls import router as usersRouter

from . import social
from .api.api import api
from .views import health

router = routers.DefaultRouter()
router.registry.extend(projectsRouter.registry)
router.registry.extend(organizationsRouter.registry)
router.registry.extend(usersRouter.registry)

if settings.BILLING_ENABLED:
    from apps.djstripe_ext.urls import router as djstripeRouter

    router.registry.extend(djstripeRouter.registry)


urlpatterns = [
    path("_health/", health),
    re_path(
        r"^favicon\.ico$",
        RedirectView.as_view(url=settings.STATIC_URL + "favicon.ico", permanent=True),
    ),
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
    ),
    path("api/", RedirectView.as_view(url="/profile/auth-tokens")),
    # OSS Sentry compat - redirect the non-api prefix url to the more typical api prefix
    path(
        "organizations/<slug:organization_slug>/issues/<int:issue_id>/events/<event_id>/json/",
        RedirectView.as_view(
            url="/api/0/organizations/%(organization_slug)s/issues/%(issue_id)s/events/%(event_id)s/json/",
        ),
    ),
    path("api/", api.urls),
    path("api/0/", include(router.urls)),
]

if "django.contrib.admin" in settings.INSTALLED_APPS:
    urlpatterns += [
        path("admin/", include("django_rest_mfa.mfa_admin.urls")),
        path("admin/", admin.site.urls),
    ]

if settings.BILLING_ENABLED:
    urlpatterns += [
        path("api/0/", include("apps.djstripe_ext.urls")),
    ]

urlpatterns += [
    path("api/0/", include("apps.projects.urls")),
    path("api/0/", include("apps.users.urls")),
    path("api/0/", include("apps.organizations_ext.urls")),
    path("api/0/", include("apps.difs.urls")),
    path("api/mfa/", include("django_rest_mfa.urls")),
    path("", include("apps.uptime.urls")),
    path("api/test/", include("test_api.urls")),
    path("rest-auth/login/", MFALoginView.as_view()),
    path("rest-auth/", include("dj_rest_auth.urls")),
    path("rest-auth/registration/", include("dj_rest_auth.registration.urls")),
    path("rest-auth/<slug:provider>/", social.MFASocialLoginView().as_view()),
    path(
        "rest-auth/<slug:provider>/connect/",
        social.GlitchTipSocialConnectView().as_view(),
    ),
    path("accounts/", include("allauth.urls")),
    path("_allauth/", include("allauth.headless.urls")),
    # These routes belong to the Angular single page app
    re_path(r"^$", TemplateView.as_view(template_name="index.html")),
    re_path(
        r"^(auth|login|register|(.*)/issues|(.*)/settings|(.*)/performance|(.*)/projects|(.*)/releases|organizations|profile|(.*)/uptime-monitors|accept|reset-password).*$",
        TemplateView.as_view(template_name="index.html"),
    ),
    # These URLS are for generating reverse urls in django, but are not really present
    # Change the activate_url in the confirm emails
    re_path(
        r"^profile/confirm-email/(?P<key>[-:\w]+)/$",
        TemplateView.as_view(),
        name="account_confirm_email",
    ),
    # Change the password_reset_confirm in the reset password emails
    re_path(
        r"^reset-password/set-new-password/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,93}-[0-9A-Za-z]{1,90})/$",
        TemplateView.as_view(),
        name="password_reset_confirm",
    ),
    path("accept/", include(invitation_backend().get_urls())),
]

if settings.BILLING_ENABLED:
    urlpatterns.append(path("stripe/", include("djstripe.urls", namespace="djstripe")))

if settings.DEBUG_TOOLBAR:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
