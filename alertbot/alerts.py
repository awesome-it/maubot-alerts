from __future__ import annotations

import colorsys
import hashlib
import pkgutil
from dataclasses import dataclass
from functools import cache
from typing import Any

from jinja2 import Environment, FunctionLoader, select_autoescape


@cache
def _load_template_source(name: str) -> str:
    # Read via the module loader's get_data so it works both from a plain
    # filesystem install and from inside a maubot .mbp zip (whose custom
    # zipimporter jinja2's PackageLoader does not recognize).
    data = pkgutil.get_data(__package__, f"templates/{name}")
    if data is None:
        raise FileNotFoundError(f"template {name!r} not found in package {__package__!r}")
    return data.decode("utf-8")


@cache
def label_color(key: str) -> dict[str, str]:
    # Deterministic pill color from label key. md5 (not builtin hash(), which is
    # per-process salted) spreads keys across the full hue spectrum. Fixed
    # saturation/lightness keep pills readable; fg is black/white by luminance.
    digest = hashlib.md5(key.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.45, 0.65)
    bg = f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"
    # Relative luminance (sRGB coefficients) picks a readable text color.
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    fg = "#000000" if luminance > 0.6 else "#ffffff"
    return {"bg": bg, "fg": fg}


_env = Environment(loader=FunctionLoader(_load_template_source), autoescape=select_autoescape())
_env.filters["label_color"] = label_color


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
        template = _env.get_template("alertgroup.jinja")
        self.message = template.render(alertgroup=self)


@dataclass
class Alert:
    fingerprint: str
    status: str
    alertmanager_data: dict
    event_id: str | None = None
    message: str | None = None
    last_actor: str | None = None
    alertgroup_id: int | None = None

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> Alert:
        return cls(fingerprint=json["fingerprint"], status=json["status"], alertmanager_data=json)

    def generate_message(self) -> None:
        template = _env.get_template("alert.jinja")
        self.message = template.render(
            status=self.status, last_actor=self.last_actor, data=self.alertmanager_data
        )
