from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .template import TemplateRenderer


class NotificationReason(StrEnum):
    # Wire values from https://github.com/prometheus/alertmanager/blob/main/notify/notify.go#L309
    DO_NOT_NOTIFY = "none"
    FIRST_NOTIFICATION = "first notification"
    NEW_ALERTS_IN_GROUP = "new alerts added"
    SOME_ALERTS_RESOLVED = "some alerts resolved"
    ALL_ALERTS_RESOLVED = "all alerts resolved"
    REPEAT_INTERVAL_ELAPSED = "repeat interval elapsed"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> NotificationReason:
        return cls.UNKNOWN


@dataclass
class AlertGroup:
    group_key: str
    status: str
    receiver: str
    group_labels: dict[str, str]
    common_labels: dict[str, str]
    common_annotations: dict[str, str]
    truncated_alerts: int
    event_id: str | None = None
    message: str | None = None
    external_url: str | None = None
    notification_reason: NotificationReason = NotificationReason.UNKNOWN
    id: int | None = None
    last_actor: str | None = None
    total_firing_alerts: int | None = None
    updated_at: dt.datetime | None = None
    firing_alerts: list[Alert] = field(default_factory=list)
    resolved_alerts: list[Alert] = field(default_factory=list)

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> AlertGroup:
        status = json["status"]
        truncated_alerts = json.get("truncatedAlerts", 0)
        common_labels = json.get("commonLabels", {})

        alerts_json = json.get("alerts", [])
        firing_json = [a for a in alerts_json if a.get("status") == "firing"]
        resolved_json = [a for a in alerts_json if a.get("status") == "resolved"]
        if firing_json and resolved_json:
            # Both types present: guarantee at least one of each, cap at 5 total.
            selected_json = [firing_json[0], resolved_json[0]]
            selected_json += (firing_json[1:] + resolved_json[1:])[:3]
        else:
            selected_json = alerts_json[:5]

        if status == "firing":
            total_firing_alerts = truncated_alerts + len(firing_json)
        else:
            total_firing_alerts = 0

        firing_alerts = []
        resolved_alerts = []
        group_labels = json["groupLabels"]
        for alert_json in selected_json:
            alert = Alert.from_json(alert_json)
            alert.generate_unique_labels(group_labels)
            if alert.status == "resolved":
                resolved_alerts.append(alert)
            else:
                firing_alerts.append(alert)

        return cls(
            group_key=json["groupKey"],
            status=status,
            receiver=json["receiver"],
            group_labels=group_labels,
            common_labels=common_labels,
            common_annotations=json["commonAnnotations"],
            truncated_alerts=truncated_alerts,
            external_url=json.get("externalURL"),
            notification_reason=NotificationReason(json.get("notification_reason")),
            total_firing_alerts=total_firing_alerts,
            firing_alerts=firing_alerts,
            resolved_alerts=resolved_alerts,
        )

    def generate_message(self, renderer: TemplateRenderer) -> None:
        self.updated_at = dt.datetime.now(dt.UTC)
        template = renderer.env.get_template("alertgroup.jinja")
        self.message = template.render(alertgroup=self)

    def set_id(self, alertgroup_id: int):
        self.id = alertgroup_id
        for a in self.firing_alerts + self.resolved_alerts:
            a.alertgroup_id = alertgroup_id

    def set_alerts(self, alerts: list[Alert]):
        for alert in alerts:
            alert.generate_unique_labels(self.group_labels)
            if alert.status == "resolved":
                self.resolved_alerts.append(alert)
            else:
                self.firing_alerts.append(alert)


@dataclass
class Alert:
    fingerprint: str
    status: str
    alertmanager_data: dict
    event_id: str | None = None
    message: str | None = None
    alertgroup_id: int | None = None
    unique_labels: dict[str, str] | None = None
    common_labels: dict[str, str] | None = None

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> Alert:
        return cls(fingerprint=json["fingerprint"], status=json["status"], alertmanager_data=json)

    def generate_message(self, renderer: TemplateRenderer) -> None:
        template = renderer.env.get_template("alert.jinja")
        self.message = template.render(
            labels=self.alertmanager_data["labels"],
            unique_labels=self.unique_labels,
            common_labels=self.common_labels,
            data=self.alertmanager_data,
        )

    def generate_unique_labels(self, group_labels: dict[str, str]) -> None:
        all_labels = self.alertmanager_data["labels"]
        self.unique_labels = {k: v for k, v in all_labels.items() if k not in group_labels}
        self.common_labels = dict(group_labels)
