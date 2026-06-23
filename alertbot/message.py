from __future__ import annotations

from typing import Optional

from mautrix.errors import MForbidden, MNotFound
from mautrix.types import (
    EventID,
    EventType,
    Format,
    MessageType,
    RelatesTo,
    RoomID,
    RoomPinnedEventsStateEventContent,
    TextMessageEventContent,
)

import alertbot
from .util.mlstrip import strip_tags


class AlertBotMessageManager:
    bot: alertbot.AlertBot

    def __init__(self, bot: alertbot.AlertBot):
        self.bot = bot

    async def send_message(
        self,
        room_id: RoomID,
        markdown: Optional[str] = None,
        html: Optional[str] = None,
        relates_to: Optional[RelatesTo] = None,
    ) -> EventID:
        if markdown:
            return await self.bot.client.send_markdown(
                room_id, markdown, allow_html=True, relates_to=relates_to
            )

        # HTML
        content = TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML)
        content.body = strip_tags(html)
        content.formatted_body = html
        content.relates_to = relates_to
        return await self.bot.client.send_message(room_id, content)

    async def edit_message(self, room_id, event_id, html):
        try:
            event = await self.bot.client.get_event(room_id, event_id)
            content = TextMessageEventContent(msgtype=MessageType.TEXT, format=Format.HTML)
            content.body = strip_tags(html)
            content.formatted_body = html
            await event.edit(content=content, allow_html=True)
        except MNotFound:
            self.bot.log.error(f"Could not find message to edit (MNotFound) in room {room_id}: {event_id}")

    async def pin_unpin_messages(
        self, room_id: RoomID, to_pin: list[EventID] = None, to_unpin: list[EventID] = None
    ) -> None:
        if not await self.bot.db.is_feature_enabled("pinning", room_id):
            return
        if to_pin is None:
            to_pin = []
        if to_unpin is None:
            to_unpin = []

        # self.bot.log.debug(f"To pin: {to_pin}; To unpin: {to_unpin}")
        async with self.bot.pinned_messages_lock:
            try:
                pinned_events = await self.bot.client.get_state_event(room_id, EventType.ROOM_PINNED_EVENTS)
            except MNotFound:
                pinned_events = RoomPinnedEventsStateEventContent(pinned=[])
            # self.bot.log.debug(f"Currently pinned events: {pinned_events}")
            for event_id in to_pin:
                if event_id not in pinned_events.pinned:
                    pinned_events.pinned.append(event_id)
            for event_id in to_unpin:
                try:
                    pinned_events.pinned.remove(event_id)
                except ValueError:
                    self.bot.log.warning(
                        f"Tried to unpin event {event_id} but it was not pinned in room {room_id}"
                    )
                    pass
            try:
                await self.bot.client.send_state_event(room_id, EventType.ROOM_PINNED_EVENTS, pinned_events)
            except MForbidden:
                message = (
                    "Pinning is enabled but failed. "
                    "To fix this increase powerlevel of bot user to 50 (default for Moderator) "
                    "or disable pinning by sending `!feature disable pinning`."
                )
                self.bot.log.error(message)
                await self.send_message(room_id, markdown=message)
