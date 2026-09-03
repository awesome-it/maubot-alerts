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

from .alerts import Alert, AlertGroup


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
        await self.bot.db.upsert_alertgroup(alertgroup)

        received_alerts = []
        for alert in data_json["alerts"]:
            received_alerts.append(Alert.from_json(alert))

        events_to_pin = []
        events_to_unpin = []
        # for alert in received_alerts:
        #     alert.event_id = await self.bot.db.get_event_id_from_fingerprint(alert.fingerprint)
        #     alert.generate_message()
        #     if alert.status == "resolved":
        #         if alert.event_id is not None:
        #             self.bot.log.debug(f"Found existing alert: {alert}")
        #             await self.bot.messages.edit_message(room_id, alert.event_id, html=alert.message)
        #             await self.bot.reactions.react_to_message(room_id, alert.event_id, "✅️")
        #             events_to_unpin.append(alert.event_id)
        #             await self.bot.db.delete_alert(alert.fingerprint)
        #         else:
        #             self.bot.log.warning(f"Received resolve for unknown alert: {alert}")
        #     elif alert.status == "firing":
        #         if alert.event_id is None:
        #             self.bot.log.debug(f"Creating new alert: {alert}")
        #             event_id = await self.bot.messages.send_message(room_id, html=alert.message)
        #             events_to_pin.append(event_id)
        #             await self.bot.db.upsert_alert(alert, event_id)
        #         else:
        #             events_to_pin.append(alert.event_id)
        #             # TODO: notify about further firings

        # alertgroup.event_id = await self.bot.db.get_event_id_from_group_key(alertgroup.group_key)
        alertgroup.generate_message()
        await self.bot.messages.send_message(room_id, html=alertgroup.message)

        await self.bot.messages.pin_unpin_messages(room_id, events_to_pin, events_to_unpin)
        await self.bot.db.touch_canary(room_id, dt.datetime.now(dt.timezone.utc))

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
