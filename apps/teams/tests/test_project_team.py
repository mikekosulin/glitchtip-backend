from django.test import TestCase
from django.urls import reverse
from model_bakery import baker

from apps.organizations_ext.models import OrganizationUserRole
from glitchtip.test_utils.test_case import GlitchTipTestCaseMixin


class ProjectTeamViewTestCase(GlitchTipTestCaseMixin, TestCase):
    def setUp(self):
        super().create_logged_in_user()
        self.url = reverse(
            "api:list_project_teams",
            kwargs={
                "organization_slug": self.organization.slug,
                "project_slug": self.project.slug,
            },
        )

    def test_project_team_list(self):
        team2 = baker.make("teams.Team", organization=self.organization)
        res = self.client.get(self.url)
        self.assertContains(res, self.team.slug)
        self.assertNotContains(res, team2.slug)

    def test_project_team_add_project(self):
        new_project = baker.make("projects.Project", organization=self.organization)
        url = reverse(
            "api:create_project_team",
            kwargs={
                "organization_slug": self.organization.slug,
                "project_slug": new_project.slug,
                "team_slug": self.team.slug,
            },
        )
        self.assertFalse(new_project.team_set.exists())
        res = self.client.post(url)
        self.assertContains(res, new_project.slug, status_code=201)
        self.assertTrue(new_project.team_set.exists())

    def test_project_team_add_project_no_perms(self):
        """User must be manager or above to manage project teams"""
        new_project = baker.make("projects.Project", organization=self.organization)
        user = baker.make("users.user")
        self.client.force_login(user)
        self.organization.add_user(user, OrganizationUserRole.MEMBER)
        url = reverse(
            "api:list_project_teams",
            kwargs={
                "organization_slug": self.organization.slug,
                "project_slug": new_project.slug,
            },
        )
        self.client.post(url + self.team.slug + "/")
        self.assertFalse(new_project.team_set.exists())

    def test_project_team_remove_project(self):
        url = reverse(
            "api:create_project_team",
            kwargs={
                "organization_slug": self.organization.slug,
                "project_slug": self.project.slug,
                "team_slug": self.team.slug,
            },
        )
        self.assertTrue(self.project.team_set.exists())
        res = self.client.delete(url)
        self.assertContains(res, self.project.slug)
        self.assertFalse(self.project.team_set.exists())
