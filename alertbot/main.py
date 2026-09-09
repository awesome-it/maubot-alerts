from __future__ import annotations

import asyncio

from maubot import Plugin
from mautrix.util.async_db import UpgradeTable
from mautrix.util.config import BaseProxyConfig

from .canary import AlertBotCanaryManager
from .command import AlertBotCommandManager
from .config import AlertBotConfig
from .database import AlertBotDatabase, upgrade_table
from .message import AlertBotMessageManager
from .reaction import AlertBotReactionManager
from .template import TemplateRenderer
from .webhook import AlertBotWebhookManager


class AlertBot(Plugin):
    pinned_messages_lock: asyncio.Lock
    db: AlertBotDatabase
    messages: AlertBotMessageManager
    reactions: AlertBotReactionManager
    canary: AlertBotCanaryManager
    webhook: AlertBotWebhookManager
    commands: AlertBotCommandManager
    templates: TemplateRenderer

    async def start(self) -> None:
        await super().start()
        if self.config:
            self.config.load_and_update()
        self.templates = TemplateRenderer(self.config)
        self.templates.validate()
        self.db = AlertBotDatabase(self, self.database)
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
    def get_config_class(cls) -> type[BaseProxyConfig] | None:
        return AlertBotConfig

    @classmethod
    def get_db_upgrade_table(cls) -> UpgradeTable:
        return upgrade_table
