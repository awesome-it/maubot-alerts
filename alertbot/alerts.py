from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from jinja2 import Environment, PackageLoader, select_autoescape


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
