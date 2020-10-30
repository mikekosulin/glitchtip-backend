from django.shortcuts import reverse
from model_bakery import baker
from glitchtip.test_utils.test_case import GlitchTipTestCase
from issues.models import Issue, EventStatus


class EventTestCase(GlitchTipTestCase):
    def setUp(self):
        self.create_user_and_project()
        self.url = reverse(
            "project-events-list",
            kwargs={
                "project_pk": f"{self.project.organization.slug}/{self.project.slug}"
            },
        )

    def test_project_events_list(self):
        event = baker.make("issues.Event", issue__project=self.project)
        baker.make("issues.Event", issue__project=self.project, _quantity=3)
        not_my_event = baker.make("issues.Event")

        with self.assertNumQueries(4):
            res = self.client.get(self.url)
        self.assertContains(res, event.pk.hex)
        self.assertNotContains(res, not_my_event.pk.hex)

    def test_events_latest(self):
        """
        Should show more recent event with previousEventID of previous/first event
        """
        event = baker.make("issues.Event", issue__project=self.project)
        event2 = baker.make("issues.Event", issue=event.issue)
        url = f"/api/0/issues/{event.issue.id}/events/latest/"
        res = self.client.get(url)
        self.assertContains(res, event2.pk.hex)
        self.assertEqual(res.data["previousEventID"], event.pk.hex)
        self.assertEqual(res.data["nextEventID"], None)

    def test_next_prev_event(self):
        """ Get next and previous event IDs that belong to same issue """
        issue1 = baker.make("issues.Issue", project=self.project)
        issue2 = baker.make("issues.Issue", project=self.project)
        baker.make("issues.Event")
        issue1_event1 = baker.make("issues.Event", issue=issue1)
        issue2_event1 = baker.make("issues.Event", issue=issue2)
        issue1_event2 = baker.make("issues.Event", issue=issue1)

        url = reverse("issue-events-latest", args=[issue1.id])
        res = self.client.get(url)
        self.assertContains(res, issue1_event2.pk.hex)
        self.assertEqual(res.data["previousEventID"], issue1_event1.pk.hex)

    def test_entries_emtpy(self):
        """ A minimal or incomplete data set should result in an empty entries array """
        data = {
            "sdk": {
                "name": "sentry",
                "version": "5",
                "packages": [],
                "integrations": [],
            },
            "type": "error",
            "title": "<unknown>",
            "culprit": "",
            "request": {
                "url": "http://localhost",
                "headers": [],
                "inferred_content_type": None,
            },
            "contexts": None,
            "metadata": {"value": "Non-Error exception"},
            "packages": None,
            "platform": "javascript",
            "exception": {
                "values": [
                    {
                        "type": "Error",
                        "value": "Non-Error exception",
                        "mechanism": {
                            "data": {"function": "<anonymous>"},
                            "type": "instrument",
                            "handled": True,
                        },
                    }
                ]
            },
        }
        event = baker.make("issues.Event", issue__project=self.project, data=data)
        res = self.client.get(self.url)
        self.assertTrue("entries" in res.data[0])

    def test_event_json(self):
        event = baker.make("issues.Event", issue__project=self.project)
        url = reverse(
            "event_json",
            kwargs={
                "org": self.organization.slug,
                "issue": event.issue.id,
                "event": event.event_id_hex,
            },
        )
        res = self.client.get(url)
        self.assertContains(res, event.event_id_hex)


class IssuesAPITestCase(GlitchTipTestCase):
    def setUp(self):
        self.create_user_and_project()
        self.url = reverse("issue-list")

    def test_issue_list(self):
        issue = baker.make("issues.Issue", project=self.project)
        not_my_issue = baker.make("issues.Issue")

        res = self.client.get(self.url)
        self.assertContains(res, issue.title)
        self.assertNotContains(res, not_my_issue.title)

    def test_issue_retrieve(self):
        issue = baker.make("issues.Issue", project=self.project)
        not_my_issue = baker.make("issues.Issue")

        url = reverse("issue-detail", args=[issue.id])
        res = self.client.get(url)
        self.assertContains(res, issue.title)

        url = reverse("issue-detail", args=[not_my_issue.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 404)

    def test_issue_last_seen(self):
        issue = baker.make("issues.Issue", project=self.project)
        events = baker.make("issues.Event", issue=issue, _quantity=2)
        res = self.client.get(self.url)
        self.assertEqual(
            res.data[0]["lastSeen"][:25], events[1].created.isoformat()[:25]
        )

    def test_issue_delete(self):
        issue = baker.make("issues.Issue", project=self.project)
        not_my_issue = baker.make("issues.Issue")

        url = reverse("issue-detail", args=[issue.id])
        res = self.client.delete(url)
        self.assertEqual(res.status_code, 204)

        url = reverse("issue-detail", args=[not_my_issue.id])
        res = self.client.delete(url)
        self.assertEqual(res.status_code, 404)

    def test_bulk_update(self):
        """ Bulk update only supports Issue status """
        issues = baker.make(Issue, project=self.project, _quantity=2)
        url = f"{self.url}?id={issues[0].id}&id={issues[1].id}"
        status_to_set = EventStatus.RESOLVED
        data = {"status": status_to_set.label}
        res = self.client.put(url, data)
        self.assertContains(res, status_to_set.label)
        issues = Issue.objects.all()
        self.assertEqual(issues[0].status, status_to_set)
        self.assertEqual(issues[1].status, status_to_set)

    def test_filter_project(self):
        baker.make(Issue, project=self.project)
        project = baker.make("projects.Project", organization=self.organization)
        project.team_set.add(self.team)
        issue = baker.make(Issue, project=project)

        res = self.client.get(self.url, {"project": project.id})
        self.assertEqual(len(res.data), 1)
        self.assertContains(res, issue.id)

    def test_issue_list_filter(self):
        project1 = self.project
        project2 = baker.make("projects.Project", organization=self.organization)
        project2.team_set.add(self.team)
        project3 = baker.make("projects.Project", organization=self.organization)
        project3.team_set.add(self.team)

        issue1 = baker.make("issues.Issue", project=project1)
        issue2 = baker.make("issues.Issue", project=project2)
        issue3 = baker.make("issues.Issue", project=project3)

        res = self.client.get(
            self.url + f"?project={project1.id}&project={project2.id}"
        )
        self.assertContains(res, issue1.title)
        self.assertContains(res, issue2.title)
        self.assertNotContains(res, issue3.title)

    def test_issue_list_sort(self):
        issue1 = baker.make("issues.Issue", project=self.project)
        issue2 = baker.make("issues.Issue", project=self.project)
        issue3 = baker.make("issues.Issue", project=self.project)

        baker.make("issues.Event", issue=issue2, _quantity=2)
        baker.make("issues.Event", issue=issue1)

        res = self.client.get(self.url)
        self.assertEqual(res.data[0]["id"], issue1.id)

        res = self.client.get(self.url + "?sort=-count")
        self.assertEqual(res.data[0]["id"], issue2.id)

        res = self.client.get(self.url + "?sort=priority")
        self.assertEqual(res.data[0]["id"], issue3.id)

        res = self.client.get(self.url + "?sort=-priority")
        self.assertEqual(res.data[0]["id"], issue2.id)

    def test_filter_is_status(self):
        """ Match sentry's usage of "is" for status filtering """
        resolved_issue = baker.make(
            Issue, status=EventStatus.RESOLVED, project=self.project
        )
        unresolved_issue = baker.make(
            Issue, status=EventStatus.UNRESOLVED, project=self.project
        )
        res = self.client.get(self.url, {"query": "is:unresolved has:platform"})
        self.assertEqual(len(res.data), 1)
        self.assertContains(res, unresolved_issue.title)
        self.assertNotContains(res, resolved_issue.title)

    def test_issue_serializer_type(self):
        """
        Ensure type field is show in serializer
        https://gitlab.com/glitchtip/glitchtip-backend/-/issues/9
        """
        issue = baker.make("issues.Issue", project=self.project)

        url = reverse("issue-detail", args=[issue.id])
        res = self.client.get(url)
        self.assertContains(res, issue.get_type_display())
