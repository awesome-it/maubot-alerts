import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Callable, Awaitable, Optional

from aiohttp.web import Request, Response
from aiohttp.web_response import json_response
from maubot import Plugin
from maubot.handlers import command, web, event
from mautrix.errors import MForbidden, MNotFound
from mautrix.types import MessageEvent, RoomID, EventID, RelatesTo, TextMessageEventContent, MessageType, Format, \
    EventType, StateEvent
from mautrix.util.async_db import UpgradeTable, Connection

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE alerts
           (
               fingerprint TEXT PRIMARY KEY,
               event_id    TEXT,
               status      TEXT
           )"""
    )

@upgrade_table.register(description="Add JSON data")
async def upgrade_v2(conn: Connection) -> None:
    await conn.execute("ALTER TABLE alerts ADD COLUMN data TEXT")

@dataclass
class Alert:
    fingerprint: str
    status: str
    alertmanager_data: dict
    event_id: Optional[str] = None
    message: Optional[str] = None

    def generate_message(self) -> None:
        if self.status == "firing":
            color = "red"
        elif self.status == "acknowledged":
            color = "orange"
        else:
            color = "green"
        self.message = (
            f"<strong><font color={color}>{self.status.upper()}: </font></strong>"
            f"{self.alertmanager_data['annotations']['description']}"
        )

class AlertBot(Plugin):
    async def get_event_id_from_fingerprint(self, fingerprint: str) -> str:
        query = """
                SELECT event_id
                FROM alerts
                WHERE fingerprint = $1 \
                """
        event_id = await self.database.fetchval(query, fingerprint)
        self.log.debug(f"fingerprint: {fingerprint} -> event_id: {event_id}")
        return event_id

    async def get_alert_from_event_id(self, event_id: str) -> Optional[Alert]:
        query = """
                SELECT *
                FROM alerts
                WHERE event_id = $1
                """
        row = await self.database.fetchrow(query, event_id)
        if row:
            alertmanager_data = json.loads(row["data"])
            self.log.debug(f"alertmanager_data: {row["data"]}")
            return Alert(fingerprint=row["fingerprint"], status=row["status"], alertmanager_data=alertmanager_data)
        return None

    async def update_alert(self, alert: Alert, event_id):
        json_data = json.dumps(alert.alertmanager_data)
        self.log.debug(f"json_data: {json_data}")
        query = """
                INSERT INTO alerts (fingerprint, event_id, status, data)
                VALUES ($1, $2, $3, $4) ON CONFLICT (fingerprint) DO
                UPDATE SET event_id = $2, status = $3, data = $4
                """
        self.log.debug(f"Upserting {alert.fingerprint}, event_id: {event_id}, status: {alert.status}")
        await self.database.execute(query, alert.fingerprint, event_id, alert.status, json_data)

    async def remove_alert_from_db(self, fingerprint) -> None:
        query = """
                DELETE
                FROM alerts
                WHERE fingerprint = $1
                """
        self.log.debug(f"Removing alert with fingerprint: {fingerprint}")
        await self.database.execute(query, fingerprint)

    async def send_message(self, room_id: RoomID, markdown: Optional[str] = None, html: Optional[str] = None,
                           relates_to: Optional[RelatesTo] = None) -> EventID:
        if markdown:
            return await self.client.send_markdown(room_id, markdown, allow_html=True, relates_to=relates_to)

        # HTML
        content = TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML)
        content.formatted_body = html
        content.relates_to = relates_to
        return await self.client.send_message(room_id, content)

    async def edit_message(self, room_id, event_id, html):
        try:
            event = await self.client.get_event(room_id, event_id)
            await event.edit(content=html, allow_html=True)
        except MNotFound:
            self.log.error(f"Could not find message to edit (MNotFound) in room {room_id}: {event_id}")

    async def react_to_message(self, room_id, event_id, reaction) -> None:
        try:
            event = await self.client.get_event(room_id, event_id)
            await event.react(reaction)
        except MNotFound:
            self.log.error(f"Could not find message to react to (MNotFound) in room {room_id}: {event_id}")

    async def call_and_handle_error(self, fn: Callable[[Request, RoomID], Awaitable[Optional[Response]]],
                                    req: Request) -> Response:
        room_id = req.match_info["room_id"].strip()

        try:
            self.authenticate(req)
            response = await fn(req, room_id)
            if not response:
                return json_response({"status": "ok"})

        except JSONDecodeError as e:
            self.log.error(f'Could not parse JSON: {e}')
            return json_response({"error": str(e)}, status=400)

        except MForbidden as e:
            self.log.error(f'Not allowed to send to "{room_id}" (Most likely the bot is not invited in the room): {e}')
            return json_response({"error": str(e)}, status=403)

    def authenticate(self, req: Request) -> None:
        return

    async def alert_message(self, req: Request, room_id: RoomID):
        data_json = await req.json()
        self.log.debug(data_json)
        received_alerts = []
        for alert in data_json['alerts']:
            received_alerts.append(
                Alert(alert['fingerprint'], status=alert['status'], alertmanager_data=alert))
        for alert in received_alerts:
            alert.event_id = await self.get_event_id_from_fingerprint(alert.fingerprint)
            alert.generate_message()
            if alert.status == "resolved":
                if alert.event_id is not None:
                    self.log.debug(f"Found existing alert: {alert}")
                    await self.edit_message(room_id, alert.event_id, html=alert.message)
                    await self.react_to_message(room_id, alert.event_id, "✅️")
                    await self.remove_alert_from_db(alert.fingerprint)
                else:
                    self.log.warning(f"Received resolve for unknown alert: {alert}")
            elif alert.status == "firing":
                if alert.event_id is None:
                    self.log.debug(f"New alert: {alert}")
                    event_id = await self.send_message(room_id, html=alert.message)
                    await self.update_alert(alert, event_id)
                else:
                    # TODO: notify about further firings
                    pass

    @web.post("/prom-alerts/{room_id}")
    async def post_prom_alerts(self, req: Request) -> Response:
        return await self.call_and_handle_error(self.alert_message, req)

    @event.on(EventType.REACTION)
    async def handle_event_reaction(self, evt: StateEvent) -> None:
        if evt.sender != self.client.mxid:
            room_id = evt.room_id
            related_event_id = evt.content.relates_to.event_id
            reaction_key = evt.content.relates_to.key.replace('\uFE0F', '').replace('\uFE0E', '')
            alert = await self.get_alert_from_event_id(related_event_id)
            self.log.debug(f"Found alert: {alert}")
            if alert and reaction_key == "👍":
                alert.status = "acknowledged"
                await self.update_alert(alert, related_event_id)
                alert.generate_message()
                await self.edit_message(room_id, related_event_id, html=alert.message)
                await self.react_to_message(room_id, related_event_id, "👍")
            elif alert and reaction_key == "✅":
                alert.status = "manually resolved"
                alert.generate_message()
                await self.edit_message(room_id, related_event_id, html=alert.message)
                await self.remove_alert_from_db(alert.fingerprint)

    @classmethod
    def get_db_upgrade_table(cls) -> UpgradeTable:
        return upgrade_table

    @command.new()
    async def ping(self, evt: MessageEvent) -> None:
        await evt.reply("pong")
