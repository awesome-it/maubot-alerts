from __future__ import annotations

import colorsys
import hashlib
import pkgutil
from functools import cache

from jinja2 import Environment, FunctionLoader, select_autoescape
from mautrix.util.config import BaseProxyConfig


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
    # Deterministic pill palette from label key. md5 (not builtin hash(), which
    # is per-process salted) spreads keys across the full hue spectrum. Same
    # hue is reused at three lightness stops so the trio always feels coherent:
    # bg (mid), bg_light (near-white tint), fg (near-black tint). Picking fg as
    # a dark same-hue shade guarantees enough contrast against both bg and
    # bg_light without falling back to plain black/white.
    digest = hashlib.md5(key.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    saturation = 0.65

    def _hex(lightness: float) -> str:
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"

    return {
        "bg": _hex(0.45),
        "bg_light": _hex(0.92),
        "fg": _hex(0.18),
    }


class TemplateRenderer:
    config: BaseProxyConfig | None
    env: Environment

    def __init__(self, config: BaseProxyConfig | None = None):
        self.config = config
        self.env = Environment(
            loader=FunctionLoader(self._load_template_source),
            autoescape=select_autoescape(),
            cache_size=0,
        )
        self.env.filters["label_color"] = label_color

    def _load_template_source(self, name: str) -> str:
        configured_source = self._get_configured_template(name)
        if configured_source:
            return configured_source
        return _load_template_source(name)

    def _get_configured_template(self, name: str) -> str | None:
        key = name.removesuffix(".jinja")
        if self.config is None:
            return None
        if isinstance(self.config, dict):
            templates = self.config.get("templates") or {}
            return templates.get(key) or None
        return self.config.get(f"templates.{key}", None) or None

    def validate(self) -> None:
        self.env.get_template("alert.jinja")
        self.env.get_template("alertgroup.jinja")
