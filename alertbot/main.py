from __future__ import annotations

import asyncio

from maubot import Plugin
from mautrix.util.async_db import UpgradeTable

from .canary import AlertBotCanaryManager
from .command import AlertBotCommandManager
from .database import AlertBotDatabase, upgrade_table
from .message import AlertBotMessageManager
from .reaction import AlertBotReactionManager
from .webhook import AlertBotWebhookManager


class AlertBot(Plugin):
    pinned_messages_lock: asyncio.Lock
    db: AlertBotDatabase
    messages: AlertBotMessageManager
    reactions: AlertBotReactionManager
    canary: AlertBotCanaryManager
    webhook: AlertBotWebhookManager
    commands: AlertBotCommandManager

    async def start(self) -> None:
        await super().start()
        self.db = AlertBotDatabase(self.database)
        self.pinned_messages_lock = asyncio.Lock()
        self.messages = AlertBotMessageManager(self)
        self.reactions = AlertBotReactionManager(self)
        self.canary = AlertBotCanaryManager(self)
        self.webhook = AlertBotWebhookManager(self)
        self.commands = AlertBotCommandManager(self)

        self.register_handler_class(self.webhook)
        self.register_handler_class(self.reactions)
        self.register_handler_class(self.commands)

        await self.canary.schedule_canary_tasks()

    async def stop(self):
        await super().stop()
        await self.canary.cancel_canary_tasks()

    @classmethod
    def get_db_upgrade_table(cls) -> UpgradeTable:
        return upgrade_table
