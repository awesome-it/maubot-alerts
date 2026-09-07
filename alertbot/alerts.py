from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from alertbot.template import TemplateRenderer


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
    notification_reason: str | None = None
    id: int | None = None
    last_actor: str | None = None
    total_firing_alerts: int | None = None
    firing_alerts: list[Alert] = field(default_factory=list)
    resolved_alerts: list[Alert] = field(default_factory=list)

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> AlertGroup:
        return cls(
            group_key=json["groupKey"],
            status=json["status"],
            receiver=json["receiver"],
            group_labels=json["groupLabels"],
            common_labels=json["commonLabels"],
            common_annotations=json["commonAnnotations"],
            truncated_alerts=json.get("truncatedAlerts", 0),
            external_url=json.get("externalURL"),
            notification_reason=json.get("notificationReason"),
        )

    def generate_message(self, renderer: TemplateRenderer) -> None:
        template = renderer.env.get_template("alertgroup.jinja")
        self.message = template.render(alertgroup=self)

    def add_alert(self, alert: Alert) -> None:
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

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> Alert:
        return cls(fingerprint=json["fingerprint"], status=json["status"], alertmanager_data=json)

    def generate_message(self, renderer: TemplateRenderer) -> None:
        template = renderer.env.get_template("alert.jinja")
        self.message = template.render(unique_labels=self.unique_labels, data=self.alertmanager_data)

    def generate_unique_labels(self, common_labels: dict[str, str]) -> None:
        all_labels = self.alertmanager_data["labels"]
        self.unique_labels = {k: v for k, v in all_labels.items() if k not in common_labels}
