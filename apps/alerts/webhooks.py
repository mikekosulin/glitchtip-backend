from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Optional

import requests
from django.conf import settings
from django.db.models import F

from .constants import RecipientType

if TYPE_CHECKING:
    from .models import Notification


@dataclass
class WebhookAttachmentField:
    title: str
    value: str
    short: bool


@dataclass
class WebhookAttachment:
    title: str
    title_link: str
    text: str
    image_url: Optional[str] = None
    color: Optional[str] = None
    fields: Optional[list[WebhookAttachmentField]] = None
    mrkdown_in: Optional[list[str]] = None


@dataclass
class MSTeamsSection:
    """
    Similar to WebhookAttachment but for MS Teams
    https://docs.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/connectors-using?tabs=cURL
    """

    activityTitle: str
    activitySubtitle: str


@dataclass
class WebhookPayload:
    alias: str
    text: str
    attachments: list[WebhookAttachment]
    sections: list[MSTeamsSection]


def send_webhook(
    url: str,
    message: str,
    attachments: Optional[list[WebhookAttachment]] = None,
    sections: Optional[list[MSTeamsSection]] = None,
):
    if not attachments:
        attachments = []
    if not sections:
        sections = []
    data = WebhookPayload(
        alias="GlitchTip", text=message, attachments=attachments, sections=sections
    )
    return requests.post(
        url, json=asdict(data), headers={"Content-type": "application/json"}, timeout=10
    )


def send_issue_as_webhook(url, issues: list, issue_count: int = 1):
    """
    Notification about issues via webhook.
    url: Webhook URL
    issues: This should be only the issues to send as attachment
    issue_count - total issues, may be greater than len(issues)
    """
    attachments: list[WebhookAttachment] = []
    sections: list[MSTeamsSection] = []
    for issue in issues:
        fields = [
            WebhookAttachmentField(
                title="Project",
                value=issue.project.name,
                short=True,
            )
        ]
        environment = (
            issue.issuetag_set.filter(tag_key__key="environment")
            .values(value=F("tag_value__value"))
            .first()
        )
        if environment:
            fields.append(
                WebhookAttachmentField(
                    title="Environment",
                    value=environment['value'],
                    short=True,
                )
            )
        release = (
            issue.issuetag_set.filter(tag_key__key="release")
            .values(value=F("tag_value__value"))
            .first()
        )
        if release:
            fields.append(
                WebhookAttachmentField(
                    title="Release",
                    value=release['value'],
                    short=False,
                )
            )
        attachments.append(
            WebhookAttachment(
                mrkdown_in=["text"],
                title=str(issue),
                title_link=issue.get_detail_url(),
                text=issue.culprit,
                color=issue.get_hex_color(),
                fields=fields,
            )
        )
        sections.append(
            MSTeamsSection(
                activityTitle=str(issue),
                activitySubtitle=f"[View Issue {issue.short_id_display}]({issue.get_detail_url()})",
            )
        )
    message = "GlitchTip Alert"
    if issue_count > 1:
        message += f" ({issue_count} issues)"
    return send_webhook(url, message, attachments, sections)


@dataclass
class DiscordField:
    name: str
    value: str
    inline: bool = False


@dataclass
class DiscordEmbed:
    title: str
    description: str
    color: int
    url: str
    fields: list[DiscordField]


@dataclass
class DiscordWebhookPayload:
    content: str
    embeds: list[DiscordEmbed]


def send_issue_as_discord_webhook(url, issues: list, issue_count: int = 1):
    embeds: list[DiscordEmbed] = []

    for issue in issues:
        fields = [
            DiscordField(
                name="Project",
                value=issue.project.name,
                inline=True,
            )
        ]
        environment = (
            issue.issuetag_set.filter(tag_key__key="environment")
            .values(value=F("tag_value__value"))
            .first()
        )
        if environment:
            fields.append(
                DiscordField(
                    name="Environment",
                    value=environment['value'],
                    inline=True,
                )
            )
        release = (
            issue.issuetag_set.filter(tag_key__key="release")
            .values(value=F("tag_value__value"))
            .first()
        )
        if release:
            fields.append(
                DiscordField(
                    name="Release",
                    value=release['value'],
                    inline=False,
                )
            )

        embeds.append(
            DiscordEmbed(
                title=str(issue),
                description=issue.culprit,
                color=int(issue.get_hex_color()[1:], 16)
                if issue.get_hex_color() is not None
                else None,
                url=issue.get_detail_url(),
                fields=fields,
            )
        )

    message = "GlitchTip Alert"
    if issue_count > 1:
        message += f" ({issue_count} issues)"

    return send_discord_webhook(url, message, embeds)


def send_discord_webhook(url: str, message: str, embeds: list[DiscordEmbed]):
    payload = DiscordWebhookPayload(content=message, embeds=embeds)
    return requests.post(url, json=asdict(payload), timeout=10)


@dataclass
class GoogleChatCard:
    header: Optional[dict] = None
    sections: Optional[list[dict]] = None

    def construct_uptime_card(self, title: str, subtitle: str, text: str, url: str):
        self.header = dict(
            title=title,
            subtitle=subtitle,
        )
        self.sections = [
            dict(
                widgets=[
                    dict(
                        decoratedText=dict(
                            text=text,
                            button=dict(
                                text="View", onClick=dict(openLink=dict(url=url))
                            ),
                        )
                    )
                ]
            )
        ]
        return self

    def construct_issue_card(self, title: str, issue):
        self.header = dict(title=title, subtitle=issue.project.name)
        section_header = "<font color='{}'>{}</font>".format(
            issue.get_hex_color(), str(issue)
        )
        widgets = []
        widgets.append(dict(decoratedText=dict(topLabel="Culprit", text=issue.culprit)))
        environment = (
            issue.issuetag_set.filter(tag_key__key="environment")
            .values(value=F("tag_value__value"))
            .first()
        )
        if environment:
            widgets.append(
                dict(decoratedText=dict(topLabel="Environment", text=environment['value']))
            )
        release = (
            issue.issuetag_set.filter(tag_key__key="release")
            .values(value=F("tag_value__value"))
            .first()
        )
        if release:
            widgets.append(
                dict(decoratedText=dict(topLabel="Release", text=release['value']))
            )
        widgets.append(
            dict(
                buttonList=dict(
                    buttons=[
                        dict(
                            text="View Issue {}".format(issue.short_id_display),
                            onClick=dict(openLink=dict(url=issue.get_detail_url())),
                        )
                    ]
                )
            )
        )
        self.sections = [dict(header=section_header, widgets=widgets)]
        return self


@dataclass
class GoogleChatWebhookPayload:
    cardsV2: list[dict[str, GoogleChatCard]] = field(default_factory=list)

    def add_card(self, card):
        return self.cardsV2.append(dict(cardId="createCardMessage", card=card))


def send_googlechat_webhook(url: str, cards: list[GoogleChatCard]):
    """
    Send Google Chat compatible message as documented in
    https://developers.google.com/chat/messages-overview
    """
    payload = GoogleChatWebhookPayload()
    [payload.add_card(card) for card in cards]
    return requests.post(url, json=asdict(payload), timeout=10)


def send_issue_as_googlechat_webhook(url, issues: list):
    cards = []
    for issue in issues:
        card = GoogleChatCard().construct_issue_card(
            title="GlitchTip Alert", issue=issue
        )
        cards.append(card)
    return send_googlechat_webhook(url, cards)


def send_webhook_notification(
    notification: "Notification", url: str, recipient_type: str
):
    issue_count = notification.issues.count()
    issues = notification.issues.all()[: settings.MAX_ISSUES_PER_ALERT]

    if recipient_type == RecipientType.DISCORD:
        send_issue_as_discord_webhook(url, issues, issue_count)
    elif recipient_type == RecipientType.GOOGLE_CHAT:
        send_issue_as_googlechat_webhook(url, issues)
    else:
        send_issue_as_webhook(url, issues, issue_count)
