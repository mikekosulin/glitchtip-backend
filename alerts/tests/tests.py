import json
from datetime import timedelta

from django.core import mail
from django.shortcuts import reverse
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker

from glitchtip import test_utils  # pylint: disable=unused-import
from glitchtip.test_utils.test_case import GlitchTipTestCase
from issues.models import EventStatus, Issue
from organizations_ext.models import OrganizationUserRole
from users.models import ProjectAlertStatus

from ..models import Notification
from ..tasks import process_event_alerts


class AlertTestCase(GlitchTipTestCase):
    def setUp(self):
        self.create_user_and_project()
        self.now = timezone.now()

    def test_alerts(self):
        baker.make(
            "alerts.ProjectAlert",
            project=self.project,
            timespan_minutes=10,
            quantity=10,
        )

        issue = baker.make("issues.Issue", project=self.project)
        baker.make("events.Event", issue=issue)

        # Not sufficient events to create alert
        process_event_alerts()
        self.assertEqual(Notification.objects.count(), 0)

        baker.make("events.Event", issue=issue, _quantity=9)

        process_event_alerts()
        self.assertEqual(Notification.objects.count(), 1)

        # Notifications have a cooldown time equal to alert timespan
        process_event_alerts()
        self.assertEqual(Notification.objects.count(), 1)

        # Notifications should not happen again for same issue
        with freeze_time(self.now + timedelta(minutes=11)):
            baker.make("events.Event", issue=issue, _quantity=10)
            process_event_alerts()
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_alert_timing(self):
        baker.make(
            "alerts.ProjectAlert",
            project=self.project,
            timespan_minutes=10,
            quantity=10,
        )
        issue = baker.make("issues.Issue", project=self.project)

        # time 0: 4 events
        # time 5: 4 more events (8 total)
        # time 11: 4 more events (12 total)
        baker.make("events.Event", issue=issue, _quantity=4)
        with freeze_time(self.now + timedelta(minutes=5)):
            baker.make("events.Event", issue=issue, _quantity=4)
            process_event_alerts()
        with freeze_time(self.now + timedelta(minutes=11)):
            baker.make("events.Event", issue=issue, _quantity=4)
            process_event_alerts()

        # Not sufficient rate of events to trigger alert.
        self.assertEqual(Notification.objects.count(), 0)

        # time 12: 4 more events (16 total, 12 in past 10 minutes)
        with freeze_time(self.now + timedelta(minutes=12)):
            baker.make("events.Event", issue=issue, _quantity=4)
            process_event_alerts()
        self.assertEqual(Notification.objects.count(), 1)

    def test_alert_one_event(self):
        """ Use same logic to send alert for every new issue """
        baker.make(
            "alerts.ProjectAlert", project=self.project, timespan_minutes=1, quantity=1,
        )
        issue = baker.make("issues.Issue", project=self.project)
        baker.make("events.Event", issue=issue)
        process_event_alerts()
        self.assertEqual(Notification.objects.count(), 1)

    def test_alert_on_regression(self):
        baker.make(
            "alerts.ProjectAlert", project=self.project, timespan_minutes=1, quantity=1,
        )

        # Make event
        with open(
            "events/test_data/incoming_events/very_small_event.json"
        ) as json_file:
            data = json.load(json_file)
        projectkey = self.project.projectkey_set.first()
        params = f"?sentry_key={projectkey.public_key}"
        url = reverse("event_store", args=[self.project.id]) + params
        self.client.post(url, data, format="json")

        # First alert
        process_event_alerts()
        self.assertEqual(len(mail.outbox), 1)

        # Mark resolved
        issue = Issue.objects.first()
        issue.status = EventStatus.RESOLVED
        issue.save()

        # Send a second event
        data["event_id"] = "cf536c31b68a473f97e579507ce155e4"
        self.client.post(url, data, format="json")
        process_event_alerts()
        self.assertEqual(len(mail.outbox), 2)

    def test_alert_subscription_default_scope(self):
        """ Subscribe by default should not result in alert emails for non-team members """
        baker.make(
            "alerts.ProjectAlert", project=self.project, timespan_minutes=1, quantity=1,
        )

        user2 = baker.make("users.user")
        self.organization.add_user(user2, OrganizationUserRole.MEMBER)

        baker.make("events.Event", issue__project=self.project)
        process_event_alerts()
        self.assertNotIn(user2.email, mail.outbox[0].to)


class AlertWithUserProjectAlert(GlitchTipTestCase):
    def setUp(self):
        self.create_user_and_project()
        self.now = timezone.now()

    def test_alert_enabled_user_project_alert_disabled(self):
        """ A user should be able to disable their own notifications """
        baker.make(
            "alerts.ProjectAlert", project=self.project, timespan_minutes=1, quantity=1,
        )
        baker.make(
            "users.UserProjectAlert",
            user=self.user,
            project=self.project,
            status=ProjectAlertStatus.OFF,
        )

        user2 = baker.make("users.user")
        org_user2 = self.organization.add_user(user2, OrganizationUserRole.ADMIN)
        self.team.members.add(org_user2)
        baker.make(
            "users.UserProjectAlert", user=user2, status=ProjectAlertStatus.ON,
        )

        user3 = baker.make("users.user")
        org_user3 = self.organization.add_user(user3, OrganizationUserRole.ADMIN)
        self.team.members.add(org_user3)
        baker.make(
            "users.UserProjectAlert",
            user=user3,
            project=self.project,
            status=ProjectAlertStatus.ON,
        )

        baker.make("events.Event", issue__project=self.project)
        process_event_alerts()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].merge_data), 2)

    def test_alert_enabled_subscribe_by_default(self):
        self.user.subscribe_by_default = False
        self.user.save()
        baker.make(
            "alerts.ProjectAlert", project=self.project, timespan_minutes=1, quantity=1,
        )

        baker.make("events.Event", issue__project=self.project)
        process_event_alerts()
        self.assertEqual(len(mail.outbox), 0)

    def test_alert_enabled_subscribe_by_default_override_false(self):
        self.user.subscribe_by_default = False
        self.user.save()
        baker.make(
            "alerts.ProjectAlert", project=self.project, timespan_minutes=1, quantity=1,
        )
        baker.make(
            "users.UserProjectAlert",
            user=self.user,
            project=self.project,
            status=ProjectAlertStatus.ON,
        )
        baker.make("events.Event", issue__project=self.project)
        process_event_alerts()
        self.assertEqual(len(mail.outbox), 1)

    def test_user_project_alert_scope(self):
        """ User project alert should not result in alert emails for non-team members """
        baker.make(
            "alerts.ProjectAlert", project=self.project, timespan_minutes=1, quantity=1,
        )

        user2 = baker.make("users.user")
        self.organization.add_user(user2, OrganizationUserRole.MEMBER)

        baker.make(
            "users.UserProjectAlert",
            user=user2,
            project=self.project,
            status=ProjectAlertStatus.ON,
        )
        baker.make("events.Event", issue__project=self.project)
        process_event_alerts()
        self.assertNotIn(user2.email, mail.outbox[0].to)
