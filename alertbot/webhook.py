from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from json import JSONDecodeError

from aiohttp.web import Request, Response
from aiohttp.web_response import json_response
from maubot.handlers import web
from mautrix.errors import MForbidden
from mautrix.types import RoomID

import alertbot

from .alerts import AlertGroup, NotificationReason


class AlertBotWebhookManager:
    bot: alertbot.AlertBot

    def __init__(self, bot: alertbot.AlertBot):
        self.bot = bot

    @web.post("/prom-alerts/{room_id}")
    async def post_prom_alerts(self, req: Request) -> Response:
        return await self._call_and_handle_error(self.alert_message, req)

    def authenticate(self, req: Request) -> None:
        return

    async def alert_message(self, req: Request, room_id: RoomID):
        data_json = await req.json()

        # This has nothing to do with alertgroups you define in prometheus / vmalert
        # This grouping is done by route.group_by in alertmanager configuration
        alertgroup = AlertGroup.from_json(data_json)
        alertgroup.event_id = await self.bot.db.get_event_id_from_group_key(alertgroup.group_key)
        alertgroup.set_id(await self.bot.db.upsert_alertgroup(alertgroup))
        # TODO: remove alerts for known alertgroups
        for a in alertgroup.firing_alerts + alertgroup.resolved_alerts:
            await self.bot.db.upsert_alert(a, None)
            a.generate_message(self.bot.templates)

        events_to_pin = []
        events_to_unpin = []
        alertgroup.generate_message(self.bot.templates)

        match alertgroup.notification_reason:
            case NotificationReason.FIRST_NOTIFICATION:
                if alertgroup.event_id is None:
                    self.bot.log.debug(f"Creating new alertgroup: {alertgroup}")
                else:
                    events_to_unpin.append(alertgroup.event_id)
                    self.bot.log.warning(f"Received first notification for known alertgroup: {alertgroup}")
                alertgroup.event_id = await self.bot.messages.send_message(room_id, html=alertgroup.message)
                events_to_pin.append(alertgroup.event_id)
                await self.bot.db.upsert_alertgroup(alertgroup)
            case (
                NotificationReason.NEW_ALERTS_IN_GROUP
                | NotificationReason.SOME_ALERTS_RESOLVED
                | NotificationReason.REPEAT_INTERVAL_ELAPSED
            ):
                if alertgroup.event_id is None:
                    self.bot.log.warning(
                        f"Received {alertgroup.notification_reason} for unknown alertgroup: {alertgroup}"
                    )
                    alertgroup.event_id = await self.bot.messages.send_message(
                        room_id, html=alertgroup.message
                    )
                    events_to_pin.append(alertgroup.event_id)
                else:
                    self.bot.log.debug(f"Received new alerts for alertgroup with id: {alertgroup.id}")
                    events_to_pin.append(alertgroup.event_id)
                    await self.bot.messages.edit_message(
                        room_id, alertgroup.event_id, html=alertgroup.message
                    )
                await self.bot.db.upsert_alertgroup(alertgroup)
            case NotificationReason.ALL_ALERTS_RESOLVED:
                if alertgroup.event_id is not None:
                    self.bot.log.debug(f"Resolved alertgroup: {alertgroup}")
                    await self.bot.messages.edit_message(
                        room_id, alertgroup.event_id, html=alertgroup.message
                    )
                    await self.bot.reactions.react_to_message(room_id, alertgroup.event_id, "✅️")
                    events_to_unpin.append(alertgroup.event_id)
                    await self.bot.db.delete_alertgroup(alertgroup)
                else:
                    self.bot.log.warning(f"Received resolve for unknown alertgroup: {alertgroup}")
            case NotificationReason.UNKNOWN:
                self.bot.log.error(
                    f"Received alertgroup notification without or with unknown notification_reason: {alertgroup}\n"
                    "Update your alertmanager instance to at least v0.32.0",
                )

        await self.bot.messages.pin_unpin_messages(room_id, events_to_pin, events_to_unpin)
        await self.bot.db.touch_canary(room_id, dt.datetime.now(dt.UTC))

    async def _call_and_handle_error(
        self,
        fn: Callable[[Request, RoomID], Awaitable[Response | None]],
        req: Request,
    ) -> Response:
        room_id = req.match_info["room_id"].strip()

        try:
            self.authenticate(req)
            response = await fn(req, room_id)
            if not response:
                return json_response({"status": "ok"})

        except JSONDecodeError as e:
            self.bot.log.error(f"Could not parse JSON: {e}")
            return json_response({"error": str(e)}, status=400)
        except MForbidden as e:
            self.bot.log.error(
                f'Not allowed to send to "{room_id}" (Most likely the bot is not invited in the room): {e}'
            )
            return json_response({"error": str(e)}, status=403)
        return json_response({"error": "internal server error"}, status=500)
