from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Alert:
    fingerprint: str
    status: str
    alertmanager_data: dict
    event_id: Optional[str] = None
    message: Optional[str] = None
    last_actor: Optional[str] = None

    def generate_message(self) -> None:
        if self.status == "firing":
            color = "red"
        elif self.status == "acknowledged":
            color = "orange"
        else:
            color = "green"
        if self.last_actor:
            actor_annotation = f" by {self.last_actor}"
        else:
            actor_annotation = ""
        self.message = (
            f"<strong><font color={color}>{self.status.upper()}{actor_annotation}: </font></strong>"
            f"<a href='{self.alertmanager_data['generatorURL']}'>{self.alertmanager_data['labels']['alertname']}</a><br/>"
            f"{self.alertmanager_data['annotations']['description']}"
        )
