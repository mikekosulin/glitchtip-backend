from datetime import timedelta
from django.utils.timezone import now
from django.conf import settings
from celery import shared_task
from events.models import Event
from .models import Issue


@shared_task
def cleanup_old_events():
    """ Delete older events and associated data  """
    days = settings.GLITCHTIP_MAX_EVENT_LIFE_DAYS
    qs = Event.objects.filter(created__lt=now() - timedelta(days=days))
    # Fast bulk delete - see https://code.djangoproject.com/ticket/9519
    qs._raw_delete(qs.db)
    # Do not optimize Issue with raw_delete as it has FK references to it.
    Issue.objects.filter(event=None).delete()


@shared_task
def update_search_index_all_issues():
    """ Very slow, force reindex of all issues """
    for issue in Issue.objects.all():
        issue.update_index()


@shared_task
def update_search_index_issue(issue_id: int):
    issue = Issue.objects.get(pk=issue_id)
    issue.update_index()
