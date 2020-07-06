from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from model_bakery import baker
from freezegun import freeze_time
from glitchtip import test_utils  # pylint: disable=unused-import
from ..tasks import set_organization_throttle


class OrganizationThrottlingTestCase(TestCase):
    @override_settings(BILLING_FREE_TIER_EVENTS=10)
    def test_non_subscriber_throttling(self):
        plan = baker.make("djstripe.Plan", active=True, amount=0)

        with freeze_time(timezone.datetime(2000, 1, 1)):
            organization = baker.make("organizations_ext.Organization")
            user = baker.make("users.user")
            organization.add_user(user)
            customer = baker.make(
                "djstripe.Customer", subscriber=organization, livemode=False
            )
            subscription = baker.make(
                "djstripe.Subscription",
                customer=customer,
                livemode=False,
                plan=plan,
                status="active",
            )
            baker.make(
                "issues.Event", issue__project__organization=organization, _quantity=3
            )
            set_organization_throttle()
            organization.refresh_from_db()
            self.assertTrue(organization.is_accepting_events)

            baker.make(
                "issues.Event", issue__project__organization=organization, _quantity=8
            )
            set_organization_throttle()
            organization.refresh_from_db()
            self.assertFalse(organization.is_accepting_events)
            self.assertTrue(mail.outbox[0])

        with freeze_time(timezone.datetime(2000, 2, 1)):
            # Month should reset throttle
            subscription.current_period_start = timezone.make_aware(
                timezone.datetime(2000, 2, 1)
            )
            subscription.save()
            set_organization_throttle()
            organization.refresh_from_db()
            self.assertTrue(organization.is_accepting_events)

            # Throttle again
            baker.make(
                "issues.Event", issue__project__organization=organization, _quantity=11
            )
            set_organization_throttle()
            organization.refresh_from_db()
            self.assertFalse(organization.is_accepting_events)
