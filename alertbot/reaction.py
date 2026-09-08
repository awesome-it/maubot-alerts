from __future__ import annotations

from enum import StrEnum

from maubot.handlers import event
from mautrix.errors import MatrixUnknownRequestError, MNotFound
from mautrix.types import EventID, EventType, RoomID, StateEvent

import alertbot
from alertbot.alerts import AlertGroup


class ReactionAction(StrEnum):
    ACKNOWLEDGE = "👍"
    UNACKNOWLEDGE = "👎"
    MANUALLY_RESOLVE = "✅"
    INVALID = ""

    @classmethod
    def _missing_(cls, value: object) -> ReactionAction:
        if value in ["👍", "👍️", "👍🏻", "👍🏽", "👍🏾", "👍🏿"]:
            return ReactionAction.ACKNOWLEDGE
        if value in ["👎", "👎️", "👎🏻", "👎🏽", "👎🏾", "👎🏿"]:
            return ReactionAction.UNACKNOWLEDGE
        if value in ["✅", "✅️"]:
            return ReactionAction.MANUALLY_RESOLVE
        return cls.INVALID


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
    async def handle_reaction_event(self, evt: StateEvent):
        if evt.sender == self.bot.client.mxid:
            return
        room_id = evt.room_id
        reaction_action = ReactionAction(evt.content.relates_to.key)
        if reaction_action == ReactionAction.INVALID:
            return
        related_event_id = evt.content.relates_to.event_id
        alertgroup = await self.bot.db.get_alertgroup_from_event_id(related_event_id)
        if not alertgroup or not alertgroup.id:
            return

        alertgroup.last_actor = evt.sender
        alertgroup.set_alerts(await self.bot.db.get_alerts_in_alertgroup(alertgroup.id))
        for a in alertgroup.firing_alerts + alertgroup.resolved_alerts:
            a.generate_message(self.bot.templates)

        await self.handle_reaction(alertgroup, related_event_id, room_id, reaction_action)

    async def handle_reaction(
        self, alertgroup: AlertGroup, event_id: EventID, room_id: RoomID, action: ReactionAction
    ) -> None:
        match action:
            case ReactionAction.ACKNOWLEDGE:
                alertgroup.status = "acknowledged"
                await self.bot.db.upsert_alertgroup(alertgroup)
                await self.bot.messages.pin_unpin_messages(room_id, to_pin=[event_id])
            case ReactionAction.UNACKNOWLEDGE:
                alertgroup.status = "firing"
                await self.bot.db.upsert_alertgroup(alertgroup)
                await self.bot.messages.pin_unpin_messages(room_id, to_pin=[event_id])
            case ReactionAction.MANUALLY_RESOLVE:
                alertgroup.status = "manually resolved"
                await self.bot.db.delete_alertgroup(alertgroup)
                await self.bot.messages.pin_unpin_messages(room_id, to_unpin=[event_id])

        alertgroup.generate_message(self.bot.templates)
        await self.bot.messages.edit_message(room_id, event_id, html=alertgroup.message)
        await self.react_to_message(room_id, event_id, action)
