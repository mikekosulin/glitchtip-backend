import asyncio
from unittest import mock

from aioresponses import aioresponses
from django.core import mail
from django.urls import reverse
from freezegun import freeze_time
from model_bakery import baker

from glitchtip.test_utils.test_case import GlitchTipTestCase
from organizations_ext.models import OrganizationUserRole
from users.models import ProjectAlertStatus

from ..constants import MonitorType
from ..models import Monitor, MonitorCheck
from ..tasks import dispatch_checks
from ..utils import fetch_all


class UptimeTestCase(GlitchTipTestCase):
    @mock.patch("glitchtip.uptime.tasks.perform_checks.run")
    def test_dispatch_checks(self, mocked):
        mock.return_value = None
        test_url = "https://example.com"
        with freeze_time("2020-01-01"):
            mon1 = baker.make(Monitor, url=test_url, monitor_type=MonitorType.GET)
            mon2 = baker.make(Monitor, url=test_url, monitor_type=MonitorType.GET)
            baker.make(MonitorCheck, monitor=mon1)

        self.assertEqual(mocked.call_count, 2)
        with freeze_time("2020-01-02"):
            baker.make(MonitorCheck, monitor=mon2)
            dispatch_checks()
        self.assertEqual(mocked.call_count, 3)

    @aioresponses()
    def test_fetch_all(self, mocked):
        test_url = "https://example.com"
        mocked.get(test_url, status=200)
        mon1 = baker.make(Monitor, url=test_url, monitor_type=MonitorType.GET)
        mocked.get(test_url, status=200)
        loop = asyncio.get_event_loop()
        monitors = list(Monitor.objects.all().values())
        results = loop.run_until_complete(fetch_all(monitors, loop))
        self.assertEqual(results[0]["id"], mon1.pk)

    @aioresponses()
    def test_monitor_checks_integration(self, mocked):
        test_url = "https://example.com"
        mocked.get(test_url, status=200)
        with freeze_time("2020-01-01"):
            mon = baker.make(Monitor, url=test_url, monitor_type=MonitorType.GET)
        self.assertEqual(mon.checks.count(), 1)

        mocked.get(test_url, status=200)
        with freeze_time("2020-01-01"):
            dispatch_checks()
        self.assertEqual(mon.checks.count(), 1)

        with freeze_time("2020-01-02"):
            with self.assertNumQueries(5):
                dispatch_checks()
        self.assertEqual(mon.checks.count(), 2)

    @aioresponses()
    @mock.patch("requests.post")
    def test_monitor_notifications(self, mocked, mock_post):
        self.create_user_and_project()
        test_url = "https://example.com"
        mocked.get(test_url, status=200)
        with freeze_time("2020-01-01"):
            baker.make(
                Monitor,
                name=test_url,
                url=test_url,
                monitor_type=MonitorType.GET,
                project=self.project,
            )
            baker.make(
                "alerts.AlertRecipient",
                alert__uptime=True,
                alert__project=self.project,
                recipient_type="email",
            )
            baker.make(
                "alerts.AlertRecipient",
                alert__uptime=True,
                alert__project=self.project,
                recipient_type="webhook",
                url="https://example.com",
            )

        mocked.get(test_url, status=500)
        with freeze_time("2020-01-02"):
            dispatch_checks()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("is down", mail.outbox[0].body)
        mock_post.assert_called_once()

        mocked.get(test_url, status=500)
        with freeze_time("2020-01-03"):
            dispatch_checks()
        self.assertEqual(len(mail.outbox), 1)

        mocked.get(test_url, status=200)
        with freeze_time("2020-01-04"):
            dispatch_checks()
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("is back up", mail.outbox[1].body)

    @aioresponses()
    def test_notification_default_scope(self, mocked):
        """Subscribe by default should not result in alert emails for non-team members"""
        self.create_user_and_project()
        test_url = "https://example.com"

        # user2 is an org member but not in a relevant team, should not receive alerts
        user2 = baker.make("users.user")
        org_user2 = self.organization.add_user(user2, OrganizationUserRole.MEMBER)
        team2 = baker.make("teams.Team", organization=self.organization)
        team2.members.add(org_user2)

        # user3 is in team3 which should receive alerts
        user3 = baker.make("users.user")
        org_user3 = self.organization.add_user(user3, OrganizationUserRole.MEMBER)
        self.team.members.add(org_user3)
        team3 = baker.make("teams.Team", organization=self.organization)
        team3.members.add(org_user3)
        team3.projects.add(self.project)

        baker.make(
            "alerts.AlertRecipient",
            alert__uptime=True,
            alert__project=self.project,
            recipient_type="email",
        )

        mocked.get(test_url, status=200)
        with freeze_time("2020-01-01"):
            baker.make(
                Monitor,
                name=test_url,
                url=test_url,
                monitor_type=MonitorType.GET,
                project=self.project,
            )

        mocked.get(test_url, status=500)
        with self.assertNumQueries(12):
            with freeze_time("2020-01-02"):
                dispatch_checks()
            self.assertNotIn(user2.email, mail.outbox[0].to)
            self.assertIn(user3.email, mail.outbox[0].to)
            self.assertEqual(len(mail.outbox[0].to), 2)

    @aioresponses()
    def test_user_project_alert_scope(self, mocked):
        """User project alert should not result in alert emails for non-team members"""
        self.create_user_and_project()
        test_url = "https://example.com"
        baker.make(
            "alerts.AlertRecipient",
            alert__uptime=True,
            alert__project=self.project,
            recipient_type="email",
        )

        user2 = baker.make("users.user")
        self.organization.add_user(user2, OrganizationUserRole.MEMBER)

        baker.make(
            "users.UserProjectAlert",
            user=user2,
            project=self.project,
            status=ProjectAlertStatus.ON,
        )

        mocked.get(test_url, status=200)
        with freeze_time("2020-01-01"):
            baker.make(
                Monitor,
                name=test_url,
                url=test_url,
                monitor_type=MonitorType.GET,
                project=self.project,
            )

        mocked.get(test_url, status=500)
        with self.assertNumQueries(12):
            with freeze_time("2020-01-02"):
                dispatch_checks()
            self.assertNotIn(user2.email, mail.outbox[0].to)

    def test_heartbeat(self):
        self.create_user_and_project()
        with freeze_time("2020-01-01"):
            monitor = baker.make(
                Monitor,
                monitor_type=MonitorType.HEARTBEAT,
                project=self.project,
            )
            baker.make(
                "alerts.AlertRecipient",
                alert__uptime=True,
                alert__project=self.project,
                recipient_type="email",
            )
            url = reverse(
                "heartbeat-check",
                kwargs={
                    "organization_slug": monitor.organization.slug,
                    "endpoint_id": monitor.endpoint_id,
                },
            )
            self.assertFalse(monitor.checks.exists())
            self.client.post(url)
            self.assertTrue(monitor.checks.filter(is_up=True).exists())
            dispatch_checks()
        self.assertTrue(monitor.checks.filter(is_up=True).exists())
        self.assertEqual(len(mail.outbox), 0)

        with freeze_time("2020-01-02"):
            dispatch_checks()
        self.assertEqual(len(mail.outbox), 1)

        with freeze_time("2020-01-03"):
            dispatch_checks()  # Still down
        self.assertEqual(len(mail.outbox), 1)

        with freeze_time("2020-01-04"):
            self.client.post(url)  # Back up
        self.assertEqual(len(mail.outbox), 2)

    def test_heartbeat_grace_period(self):
        # Don't alert users when heartbeat check has never come in
        self.create_user_and_project()
        baker.make(Monitor, monitor_type=MonitorType.HEARTBEAT, project=self.project)
        dispatch_checks()
        self.assertEqual(len(mail.outbox), 0)
