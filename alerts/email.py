from django.db.models import Q
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from users.models import ProjectAlertStatus

User = get_user_model()


def send_email_notification(notification):
    single_template_html = "issue-drip.html"
    multiple_template_html = "multiple-issues-drip.html"

    subject = "GlitchTip"
    issue_count = notification.issues.count()
    first_issue = notification.issues.all().first()
    if issue_count == 1:
        subject = f"Error in {first_issue.project}: {first_issue.title}"
    elif issue_count > 1:
        subject = f"{issue_count} errors reported in {first_issue.project}"

    base_url = settings.GLITCHTIP_URL.geturl()
    org_slug = first_issue.project.organization.slug

    text_content = f"Errors reported in {first_issue.project}:\n\n"
    for issue in notification.issues.all():
        text_content += f"{issue.title}\n"
        text_content += f"{base_url}/{org_slug}/issues/{issue.id}\n\n"

    settings_link = (
        f"{base_url}/{org_slug}/settings/projects/{first_issue.project.slug}"
    )

    if issue_count == 1:
        issue_link = f"{base_url}/{org_slug}/issues/{first_issue.id}"
        html_content = render_to_string(
            single_template_html,
            {
                "issue_title": first_issue.title,
                "project_name": first_issue.project,
                "base_url": base_url,
                "issue_link": issue_link,
                "project_notification_settings_link": settings_link,
            },
        )
    elif issue_count > 1:
        project_link = f"{base_url}/{org_slug}/issues?project={first_issue.project.id}"
        html_content = render_to_string(
            multiple_template_html,
            {
                "org_slug": org_slug,
                "project_notification_settings_link": settings_link,
                "issues": notification.issues.all(),
                "project_name": first_issue.project,
                "project_link": project_link,
            },
        )

    users = User.objects.filter(
        organizations_ext_organization__projects__projectalert__notification=notification
    ).exclude(
        Q(
            userprojectalert__project=notification.project_alert.project,
            userprojectalert__status=ProjectAlertStatus.OFF,
        )
        | Q(subscribe_by_default=False, userprojectalert=None),
    )
    if not users.exists():
        return
    to = users.values_list("email", flat=True)
    msg = EmailMultiAlternatives(subject, text_content, to=to)
    msg.merge_data = {user.email: {"unique_id": user.id} for user in users}
    msg.attach_alternative(html_content, "text/html")
    msg.send()
