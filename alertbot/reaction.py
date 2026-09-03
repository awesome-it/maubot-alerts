from __future__ import annotations

from maubot.handlers import event
from mautrix.errors import MatrixUnknownRequestError, MNotFound
from mautrix.types import EventType, StateEvent

import alertbot


class AlertBotReactionManager:
    bot: alertbot.AlertBot

    def __init__(self, bot: alertbot.AlertBot):
        self.bot = bot

    async def react_to_message(self, room_id, event_id, reaction) -> None:
        try:
            event = await self.bot.client.get_event(room_id, event_id)
            await event.react(reaction)
        except MNotFound:
            self.bot.log.error(
                f"Could not find message to react to (MNotFound) in room {room_id}: {event_id}"
            )
        except MatrixUnknownRequestError as e:
            self.bot.log.error(f"Error while reacting to message {event_id} in room {room_id}: {e}")

    @event.on(EventType.REACTION)
    async def handle_reaction(self, evt: StateEvent):
        if evt.sender != self.bot.client.mxid:
            room_id = evt.room_id
            related_event_id = evt.content.relates_to.event_id
            reaction_key = evt.content.relates_to.key
            alert = await self.bot.db.get_alert_from_event_id(related_event_id)
            self.bot.log.debug(f"Received reaction {reaction_key} to alert: {alert}")
            if alert and reaction_key in ["👍", "👍️", "👍🏻", "👍🏽", "👍🏾", "👍🏿"]:
                alert.status = "acknowledged"
                alert.last_actor = evt.sender
                alert.generate_message()
                await self.bot.messages.edit_message(room_id, related_event_id, html=alert.message)
                await self.react_to_message(room_id, related_event_id, reaction_key)
                await self.bot.db.upsert_alert(alert, related_event_id)
            elif alert and reaction_key in ["✅", "✅️"]:
                alert.status = "manually resolved"
                alert.last_actor = evt.sender
                alert.generate_message()
                await self.bot.messages.edit_message(room_id, related_event_id, html=alert.message)
                await self.react_to_message(room_id, related_event_id, reaction_key)
                await self.bot.messages.pin_unpin_messages(room_id, to_unpin=[related_event_id])
                await self.bot.db.delete_alert(alert.fingerprint)
            elif (
                alert
                and alert.status == "acknowledged"
                and reaction_key in ["👎", "👎️", "👎🏻", "👎🏽", "👎🏾", "👎🏿"]
            ):
                alert.status = "firing"
                alert.last_actor = evt.sender
                alert.generate_message()
                await self.bot.messages.edit_message(room_id, related_event_id, html=alert.message)
                await self.react_to_message(room_id, related_event_id, reaction_key)
                await self.bot.messages.pin_unpin_messages(room_id, to_pin=[related_event_id])
                await self.bot.db.upsert_alert(alert, related_event_id)
