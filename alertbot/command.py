from __future__ import annotations

import datetime as dt

from maubot.handlers import command
from mautrix.types import (
    MessageEvent,
)

import alertbot


class AlertBotCommandManager:
    bot: alertbot.AlertBot

    def __init__(self, bot: alertbot.AlertBot):
        self.bot = bot

    @command.new()
    async def ping(self, evt: MessageEvent) -> None:
        await evt.reply("pong")

    @command.new(name="feature", help="Enable or disable a feature in this room")
    @command.argument("action", pass_raw=True, required=True, matches="enable|disable")
    @command.argument("name", pass_raw=True, required=True, matches="pinning|canary")
    @command.argument("interval", pass_raw=True, matches=r"\d*")
    async def feature_toggle(self, evt: MessageEvent, action: str, name: str, interval: str) -> None:
        self.bot.log.debug(f"Received {action}: {evt}")
        room_id = evt.room_id
        action = action.lower().strip()
        name = name.lower().strip()
        enabled = action == "enable"

        if enabled:
            await self.bot.db.enable_feature(name, room_id)
        else:
            await self.bot.db.disable_feature(name, room_id)

        if name == "canary" and enabled:
            if interval is None or interval == "":
                interval = dt.timedelta(minutes=5)
            else:
                interval = dt.timedelta(seconds=int(interval))
            await self.bot.db.upsert_canary(
                room_id,
                interval,
                dt.datetime.fromtimestamp(0, dt.timezone.utc),
            )
            await self.bot.canary.schedule_canary_tasks()
        elif name == "canary" and not enabled:
            await self.bot.db.delete_canary(room_id)
            await self.bot.canary.schedule_canary_tasks()

        await evt.reply(f"Feature {name}: {action}d")
