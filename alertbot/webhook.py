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
        alertgroup.event_id = await self.bot.db.get_event_id_from_group_key(alertgroup.group_key)
        await self.bot.db.upsert_alertgroup(alertgroup)

        alerts_json = data_json["alerts"]
        firing_json = [a for a in alerts_json if a.get("status") == "firing"]
        resolved_json = [a for a in alerts_json if a.get("status") == "resolved"]
        if firing_json and resolved_json:
            # Both types present: guarantee at least one of each, cap at 5 total.
            selected_json = [firing_json[0], resolved_json[0]]
            selected_json += (firing_json[1:] + resolved_json[1:])[:3]
        else:
            selected_json = alerts_json[:5]

        for alert_json in selected_json:
            alert = Alert.from_json(alert_json)
            alert.alertgroup_id = alertgroup.id
            alert.generate_unique_labels(alertgroup.common_labels)
            alert.generate_message()
            alertgroup.add_alert(alert)
            await self.bot.db.upsert_alert(alert, None)

        events_to_pin = []
        events_to_unpin = []
        alertgroup.generate_message()
        if alertgroup.status == "firing":
            if alertgroup.event_id is None:
                self.bot.log.debug(f"Creating new alertgroup: {alertgroup}")
                alertgroup.event_id = await self.bot.messages.send_message(room_id, html=alertgroup.message)
                events_to_pin.append(alertgroup.event_id)
                await self.bot.db.upsert_alertgroup(alertgroup)
            else:
                events_to_pin.append(alertgroup.event_id)
                await self.bot.messages.edit_message(room_id, alertgroup.event_id, html=alertgroup.message)
        elif alertgroup.status == "resolved":
            if alertgroup.event_id is not None:
                self.bot.log.debug(f"Resolved alertgroup: {alertgroup}")
                await self.bot.messages.edit_message(room_id, alertgroup.event_id, html=alertgroup.message)
                await self.bot.reactions.react_to_message(room_id, alertgroup.event_id, "✅️")
                events_to_unpin.append(alertgroup.event_id)
                await self.bot.db.delete_alertgroup(alertgroup)
            else:
                self.bot.log.warning(f"Received resolve for unknown alertgroup: {alertgroup}")

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
