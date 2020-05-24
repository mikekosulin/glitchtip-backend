from unittest.mock import patch
from django.shortcuts import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from model_bakery import baker
from glitchtip import test_utils  # pylint: disable=unused-import


class SubscriptionAPITestCase(APITestCase):
    def setUp(self):
        self.user = baker.make("users.user")
        self.organization = baker.make("organizations_ext.Organization")
        self.organization.add_user(self.user)
        self.client.force_login(self.user)
        self.url = reverse("subscription-list")

    def test_list(self):
        customer = baker.make("djstripe.Customer", subscriber=self.organization)
        subscription = baker.make(
            "djstripe.Subscription", customer=customer, livemode=False
        )

        subscription2 = baker.make("djstripe.Subscription", livemode=False)
        subscription3 = baker.make(
            "djstripe.Subscription", customer=customer, livemode=True
        )

        res = self.client.get(self.url)
        self.assertContains(res, subscription.id)
        self.assertNotContains(res, subscription2.id)
        self.assertNotContains(res, subscription3.id)

    def test_detail(self):
        customer = baker.make("djstripe.Customer", subscriber=self.organization)
        subscription = baker.make(
            "djstripe.Subscription",
            customer=customer,
            livemode=False,
            created=timezone.make_aware(timezone.datetime(2020, 1, 2)),
        )
        # Should only get most recent
        baker.make(
            "djstripe.Subscription",
            customer=customer,
            livemode=False,
            created=timezone.make_aware(timezone.datetime(2020, 1, 1)),
        )
        baker.make("djstripe.Subscription")
        url = reverse("subscription-detail", args=[self.organization.slug])
        res = self.client.get(url)
        self.assertContains(res, subscription.id)

    @patch("djstripe.models.Customer.subscribe")
    def test_create(self, djstripe_customer_subscribe_mock):
        customer = baker.make(
            "djstripe.Customer", subscriber=self.organization, livemode=False
        )
        plan = baker.make("djstripe.Plan", amount=0)
        subscription = baker.make(
            "djstripe.Subscription", customer=customer, livemode=False,
        )
        djstripe_customer_subscribe_mock.return_value = subscription
        data = {"plan": plan.id, "organization": self.organization.id}
        res = self.client.post(self.url, data)
        self.assertEqual(res.data["plan"], plan.id)

    def test_create_invalid_org(self):
        """ Only owners may create subscriptions """
        user = baker.make("users.user")  # Non owner member
        plan = baker.make("djstripe.Plan", amount=0)
        self.organization.add_user(user)
        self.client.force_login(user)
        data = {"plan": plan.id, "organization": self.organization.id}
        res = self.client.post(self.url, data)
        self.assertEqual(res.status_code, 400)


class SubscriptionIntegrationTestCase(APITestCase):
    def setUp(self):
        self.user = baker.make("users.user")
        self.organization = baker.make("organizations_ext.Organization")
        self.organization.add_user(self.user)
        # Make these in this manner to avoid syncing data to stripe actual
        self.plan = baker.make("djstripe.Plan", active=True, amount=0)
        self.customer = baker.make(
            "djstripe.Customer", subscriber=self.organization, livemode=False
        )
        self.client.force_login(self.user)
        self.list_url = reverse("subscription-list")
        self.detail_url = reverse("subscription-detail", args=[self.organization.slug])

    @patch("djstripe.models.Customer.subscribe")
    def test_new_org_flow(self, djstripe_customer_subscribe_mock):
        """ Test checking if subscription exists and when not, creating a free tier one """
        res = self.client.get(self.detail_url)
        self.assertFalse(res.data["id"])  # No subscription, user should create one

        subscription = baker.make(
            "djstripe.Subscription", customer=self.customer, livemode=False,
        )
        djstripe_customer_subscribe_mock.return_value = subscription

        data = {"plan": self.plan.id, "organization": self.organization.id}
        res = self.client.post(self.list_url, data)
        self.assertContains(res, self.plan.id, status_code=201)
        djstripe_customer_subscribe_mock.assert_called_once()

        res = self.client.get(self.detail_url)
        self.assertEqual(res.data["id"], subscription.id)
