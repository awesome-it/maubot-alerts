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
            alertgroup = await self.bot.db.get_alertgroup_from_event_id(related_event_id)
            self.bot.log.debug(f"Received reaction {reaction_key} to alert: {alertgroup}")
            if alertgroup and reaction_key in ["👍", "👍️", "👍🏻", "👍🏽", "👍🏾", "👍🏿"]:
                alertgroup.status = "acknowledged"
                alertgroup.last_actor = evt.sender
                alertgroup.generate_message()
                await self.bot.messages.edit_message(room_id, related_event_id, html=alertgroup.message)
                await self.react_to_message(room_id, related_event_id, reaction_key)
                await self.bot.db.upsert_alertgroup(alertgroup)
            elif alertgroup and reaction_key in ["✅", "✅️"]:
                alertgroup.status = "manually resolved"
                alertgroup.last_actor = evt.sender
                alertgroup.generate_message()
                await self.bot.messages.edit_message(room_id, related_event_id, html=alertgroup.message)
                await self.react_to_message(room_id, related_event_id, reaction_key)
                await self.bot.messages.pin_unpin_messages(room_id, to_unpin=[related_event_id])
                await self.bot.db.delete_alertgroup(alertgroup)
            elif (
                alertgroup
                and alertgroup.status == "acknowledged"
                and reaction_key in ["👎", "👎️", "👎🏻", "👎🏽", "👎🏾", "👎🏿"]
            ):
                alertgroup.status = "firing"
                alertgroup.last_actor = evt.sender
                alertgroup.generate_message()
                await self.bot.messages.edit_message(room_id, related_event_id, html=alertgroup.message)
                await self.react_to_message(room_id, related_event_id, reaction_key)
                await self.bot.messages.pin_unpin_messages(room_id, to_pin=[related_event_id])
                await self.bot.db.upsert_alertgroup(alertgroup)
