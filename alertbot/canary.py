from __future__ import annotations

import asyncio
import datetime as dt

from mautrix.types import RoomID

import alertbot


class AlertBotCanaryManager:
    bot: alertbot.AlertBot
    canary_tasks: list[asyncio.Future]

    def __init__(self, bot: alertbot.AlertBot):
        self.bot = bot
        self.canary_tasks = []

    async def _check_canary(self, room_id: RoomID, interval: dt.timedelta) -> None:
        self.bot.log.debug(f"Starting canary loop for {room_id}")
        while True:
            self.bot.log.debug(f"Checking canary for {room_id}")
            last_successful_post = await self.bot.db.get_canary_last_post(room_id)
            if not last_successful_post:
                # TODO: fix database out of sync
                return
            if dt.datetime.now(dt.timezone.utc) - last_successful_post > interval:
                self.bot.log.error(f"CANARY IS DEAD in room {room_id}")
                message = (
                    f"<h1><font color=red>CANARY IS DEAD. </font></h1>"
                    f"The canary alert has not been received within the last {interval.total_seconds()} seconds. "
                    "Check your alertmanager instances."
                )
                await self.bot.messages.send_message(room_id, html=message)
            else:
                self.bot.log.debug(f"Canary is alive in room {room_id}")
            await asyncio.sleep(interval.total_seconds())

    async def check_canary(self, room_id: RoomID, interval: dt.timedelta) -> None:
        try:
            await self._check_canary(room_id, interval)
        except asyncio.CancelledError:
            self.bot.log.debug("Canary checking stopped")
            pass
        except Exception:
            self.bot.log.exception("Failed to check canary")

    async def schedule_canary_tasks(self) -> None:
        await self.cancel_canary_tasks()
        self.canary_tasks = []
        for room_id, interval in await self.bot.db.get_canaries():
            room_id = RoomID(room_id)
            task = asyncio.create_task(self.check_canary(room_id, interval))
            self.canary_tasks.append(task)

    async def cancel_canary_tasks(self) -> None:
        for task in self.canary_tasks:
            task.cancel()
