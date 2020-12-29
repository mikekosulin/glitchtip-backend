import copy
import uuid
import string
import random
from django.utils import timezone
from . import django_error_factory
from .csp import mdn_sample_csp

events = django_error_factory.all_django_events
events.append(mdn_sample_csp)


def get_random_string(length=16):
    letters = string.ascii_lowercase
    result_str = "".join(random.choice(letters) for i in range(length))
    return result_str


def make_event_unique(event, unique_issue=False):
    """ Assign event a random new event_id and current timestamp """
    new_event = copy.deepcopy(event)
    new_event["event_id"] = uuid.uuid4().hex
    new_event["timestamp"] = timezone.now().isoformat()
    if unique_issue:
        title = get_random_string()
        if "message" in new_event:
            new_event["message"] = title
        elif "exception" in new_event:
            new_event["exception"]["values"][0]["value"] = title
        elif "csp-report" in new_event:
            new_event["csp-report"]["document-uri"] = title
    return new_event


def generate_random_event(unique_issue=False):
    """ Return a random event from library of samples with unique event id """
    event = random.choice(events)  # nosec
    result = make_event_unique(event, unique_issue)

    return result
