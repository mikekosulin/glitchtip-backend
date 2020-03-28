from django.shortcuts import reverse
from rest_framework.test import APITestCase
from users.models import User


class TestAPITestCase(APITestCase):
    def test_seed_data(self):
        with self.settings(ENABLE_TEST_API=True):
            url = reverse("seed_data")
            res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(User.objects.all().count(), 1)

    def test_disabled_test_api(self):
        with self.settings(ENABLE_TEST_API=False):
            url = reverse("seed_data")
            res = self.client.post(url)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(User.objects.all().count(), 0)
