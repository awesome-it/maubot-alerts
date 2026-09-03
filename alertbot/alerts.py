from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from jinja2 import Environment, PackageLoader, select_autoescape


@dataclass
class AlertGroup:
    group_key: str
    status: str
    receiver: str
    group_labels: dict[str, str]
    common_labels: dict[str, str]
    common_annotations: dict[str, str]
    truncated_alerts: int
    event_id: Optional[str] = None
    message: Optional[str] = None
    external_url: str | None = None
    notification_reason: str | None = None
    id: int | None = None

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

    def generate_message(self) -> None:
        env = Environment(loader=PackageLoader("alertbot", "templates"), autoescape=select_autoescape())
        template = env.get_template("alertgroup.jinja")
        self.message = template.render(alertgroup=self)


@dataclass
class Alert:
    fingerprint: str
    status: str
    alertmanager_data: dict
    event_id: Optional[str] = None
    message: Optional[str] = None
    last_actor: Optional[str] = None
    alertgroup_id: Optional[int] = None

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> Alert:
        return cls(fingerprint=json["fingerprint"], status=json["status"], alertmanager_data=json)

    def generate_message(self) -> None:
        env = Environment(loader=PackageLoader("alertbot", "templates"), autoescape=select_autoescape())
        template = env.get_template("alert.jinja")
        self.message = template.render(
            status=self.status, last_actor=self.last_actor, data=self.alertmanager_data
        )
