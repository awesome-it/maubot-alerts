from __future__ import annotations

import datetime as dt
import json
from typing import Any

from mautrix.util.async_db import Connection, Database, UpgradeTable

import alertbot

from .alerts import Alert, AlertGroup


class AlertBotDatabase:
    bot: alertbot.AlertBot

    def __init__(self, bot: alertbot.AlertBot, db: Database):
        self.bot = bot
        self._db = db

    # --- alertgroups ---

    async def get_event_id_from_group_key(self, group_key: str):
        self.bot.log.debug(f"Getting event id from group key {group_key}")
        return await self._db.fetchval("SELECT event_id FROM alertgroups WHERE group_key = $1", group_key)

    async def get_alertgroup_row(self, event_id: str) -> Any | None:
        return await self._db.fetchrow(
            "SELECT * FROM alertgroups WHERE event_id = $1",
            event_id,
        )

    async def get_alertgroup_from_event_id(self, event_id: str) -> AlertGroup | None:
        row = await self.get_alertgroup_row(event_id)
        # self.bot.log.debug(f"get_alertgroup_from_event_id: {event_id} -> {row}")
        if row:
            return AlertGroup(
                group_key=row["group_key"],
                status=row["status"],
                receiver=row["receiver"],
                group_labels=json.loads(row["group_labels"]),
                common_labels=json.loads(row["common_labels"]),
                common_annotations=json.loads(row["common_annotations"]),
                truncated_alerts=row["truncated_alerts"],
                event_id=row["event_id"],
                external_url=row["external_url"],
                notification_reason=row["notification_reason"],
                id=row["id"],
            )
        return None

    async def upsert_alertgroup(
        self,
        alertgroup: AlertGroup,
    ) -> None:
        new_id = await self._db.fetchval(
            """
            INSERT INTO alertgroups (event_id,
                                     group_key,
                                     status,
                                     receiver,
                                     group_labels,
                                     common_labels,
                                     common_annotations,
                                     truncated_alerts,
                                     external_url,
                                     notification_reason)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8, $9, $10)
            ON CONFLICT (group_key)
                DO UPDATE SET event_id            = EXCLUDED.event_id,
                              status              = EXCLUDED.status,
                              receiver            = EXCLUDED.receiver,
                              group_labels        = EXCLUDED.group_labels,
                              common_labels       = EXCLUDED.common_labels,
                              common_annotations  = EXCLUDED.common_annotations,
                              truncated_alerts    = EXCLUDED.truncated_alerts,
                              external_url        = EXCLUDED.external_url,
                              notification_reason = EXCLUDED.notification_reason
            RETURNING id
            """,
            alertgroup.event_id,
            alertgroup.group_key,
            alertgroup.status,
            alertgroup.receiver,
            json.dumps(alertgroup.group_labels),
            json.dumps(alertgroup.common_labels),
            json.dumps(alertgroup.common_annotations),
            alertgroup.truncated_alerts,
            alertgroup.external_url,
            alertgroup.notification_reason,
        )
        alertgroup.id = int(new_id)

    async def delete_alertgroup(self, alertgroup: AlertGroup) -> None:
        await self._db.execute("DELETE FROM alertgroups WHERE id = $1", alertgroup.id)

    # --- alerts ---

    async def get_event_id_from_fingerprint(self, fingerprint: str) -> str | None:
        return await self._db.fetchval("SELECT event_id FROM alerts WHERE fingerprint = $1", fingerprint)

    async def get_alert_row(self, event_id: str) -> Any | None:
        return await self._db.fetchrow(
            "SELECT * FROM alerts WHERE event_id = $1",
            event_id,
        )

    async def get_alert_from_event_id(self, event_id: str) -> Alert | None:
        row = await self.get_alert_row(event_id)
        # self.bot.log.debug(f"get_alert_from_event_id: {event_id} -> {row}")
        if row:
            alertmanager_data = json.loads(row["data"])
            return Alert(
                fingerprint=row["fingerprint"],
                status=row["status"],
                alertmanager_data=alertmanager_data,
            )
        return None

    async def upsert_alert(self, alert: Alert, event_id: str | None) -> None:
        # log.debug(f"upsert_alert: {alert}, event_id: {event_id}")
        json_data = json.dumps(alert.alertmanager_data)
        await self._db.execute(
            """
            INSERT INTO alerts (fingerprint, event_id, status, data, last_actor, alertgroup_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (fingerprint) DO UPDATE SET event_id      = $2,
                                                    status        = $3,
                                                    data          = $4,
                                                    last_actor    = $5,
                                                    alertgroup_id = $6

            """,
            alert.fingerprint,
            event_id,
            alert.status,
            json_data,
            alert.last_actor,
            alert.alertgroup_id,
        )

    async def delete_alert(self, fingerprint: str) -> None:
        # self.bot.log.debug(f"delete_alert: {fingerprint}")
        await self._db.execute("DELETE FROM alerts WHERE fingerprint = $1", fingerprint)

    # --- features ---

    async def is_feature_enabled(self, feature: str, room_id: str) -> bool:
        row = await self._db.fetchrow(
            "SELECT feature FROM features WHERE feature = $1 AND room_id = $2",
            feature,
            room_id,
        )
        return row is not None

    async def enable_feature(self, feature: str, room_id: str) -> None:
        await self._db.execute(
            """
            INSERT INTO features (feature, room_id)
            VALUES ($1, $2)
            ON CONFLICT (feature, room_id) DO NOTHING
            """,
            feature,
            room_id,
        )

    async def disable_feature(self, feature: str, room_id: str) -> None:
        await self._db.execute(
            "DELETE FROM features WHERE feature = $1 AND room_id = $2",
            feature,
            room_id,
        )

    # --- canaries ---

    async def get_canaries(self) -> list[tuple[str, dt.timedelta]]:
        rows = await self._db.fetch("SELECT room_id, interval FROM canaries")
        return [(row["room_id"], row["interval"]) for row in rows]

    async def upsert_canary(
        self, room_id: str, interval: dt.timedelta, last_successful_post: dt.datetime
    ) -> None:
        await self._db.execute(
            """
            INSERT INTO canaries (room_id, interval, last_successful_post)
            VALUES ($1, $2, $3)
            ON CONFLICT (room_id) DO UPDATE SET room_id              = $1,
                                                interval             = $2,
                                                last_successful_post = $3
            """,
            room_id,
            interval,
            last_successful_post,
        )

    async def delete_canary(self, room_id: str) -> None:
        await self._db.execute("DELETE FROM canaries WHERE room_id = $1", room_id)

    async def touch_canary(self, room_id: str, last_successful_post: dt.datetime) -> None:
        await self._db.execute(
            "UPDATE canaries SET last_successful_post = $1 WHERE room_id = $2",
            last_successful_post,
            room_id,
        )

    async def get_canary_last_post(self, room_id: str) -> dt.datetime | None:
        return await self._db.fetchval(
            "SELECT last_successful_post FROM canaries WHERE room_id = $1", room_id
        )


upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE alerts
        (
            fingerprint TEXT PRIMARY KEY,
            event_id    TEXT,
            status      TEXT
        )
        """
    )


@upgrade_table.register(description="Add JSON data")
async def upgrade_v2(conn: Connection) -> None:
    await conn.execute("ALTER TABLE alerts ADD COLUMN data TEXT")


@upgrade_table.register(description="Add last_actor column")
async def upgrade_v3(conn: Connection) -> None:
    await conn.execute("ALTER TABLE alerts ADD COLUMN last_actor TEXT")


@upgrade_table.register(description="Add per-room feature table")
async def upgrade_v4(conn: Connection) -> None:
    await conn.execute("""
                       CREATE TABLE features
                       (
                           feature TEXT,
                           room_id TEXT,
                           PRIMARY KEY (feature, room_id)
                       )
                       """)


@upgrade_table.register(description="Add per-room canaries")
async def upgrade_v5(conn: Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE canaries
        (
            room_id              TEXT,
            interval             INTERVAL,
            last_successful_post TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (room_id)
        )
        """
    )


@upgrade_table.register(description="Add alert groups")
async def upgrade_v6(conn: Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE alertgroups
        (
            id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id            TEXT,
            group_key           TEXT    NOT NULL UNIQUE,
            status              TEXT    NOT NULL,
            receiver            TEXT    NOT NULL,
            group_labels        JSONB   NOT NULL,
            common_labels       JSONB   NOT NULL,
            common_annotations  JSONB   NOT NULL,
            truncated_alerts    INTEGER NOT NULL,
            external_url        TEXT,
            notification_reason TEXT
        );
        ALTER TABLE alerts
            ADD COLUMN alertgroup_id INTEGER REFERENCES alertgroups ON DELETE CASCADE ON UPDATE CASCADE;
        """
    )
