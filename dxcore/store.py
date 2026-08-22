from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

from dxcore.config import LOCAL_DB_PATH
from dxcore.schema import SHEET_SCHEMAS


SHEET_TABLES = {
    "Users": "users",
    "Locations": "locations",
    "Logging Entries": "logs",
    "Bandscan": "bandscan",
    "Import Batches": "import_batches",
    "Announcements": "announcements",
    "Support Tickets": "support_tickets",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat()


class LocalStore:
    """SQLite-backed development adapter. It never connects to Google."""

    def __init__(self, path: Path = LOCAL_DB_PATH) -> None:
        self.path = Path(path)
        self.sync_enabled = False
        self.sync_error = ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL,
                    theme_name TEXT NOT NULL DEFAULT 'Midnight blue',
                    large_text INTEGER NOT NULL DEFAULT 0,
                    reduce_motion INTEGER NOT NULL DEFAULT 0,
                    walkthrough_complete INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS locations (
                    location_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    city TEXT NOT NULL,
                    region TEXT NOT NULL,
                    country TEXT NOT NULL,
                    grid TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    is_home INTEGER NOT NULL DEFAULT 0,
                    created_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_locations_user ON locations(user_id);
                CREATE TABLE IF NOT EXISTS logs (
                    log_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    location_id TEXT NOT NULL,
                    station_id TEXT NOT NULL,
                    band TEXT NOT NULL,
                    frequency REAL NOT NULL,
                    call TEXT NOT NULL,
                    station_city TEXT NOT NULL,
                    station_region TEXT NOT NULL,
                    station_country TEXT NOT NULL,
                    station_county TEXT NOT NULL,
                    station_grid TEXT NOT NULL,
                    station_latitude REAL,
                    station_longitude REAL,
                    reception_utc TEXT NOT NULL,
                    distance_miles REAL,
                    propagation TEXT NOT NULL,
                    is_sdr INTEGER NOT NULL DEFAULT 0,
                    is_portable INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL,
                    source TEXT NOT NULL,
                    import_batch_id TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL DEFAULT '',
                    deleted_utc TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_logs_owner_time ON logs(user_id, reception_utc);
                CREATE INDEX IF NOT EXISTS idx_logs_unique_station ON logs(user_id, station_id);
                CREATE TABLE IF NOT EXISTS bandscan (
                    bandscan_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    location_id TEXT NOT NULL,
                    band TEXT NOT NULL,
                    frequency REAL NOT NULL,
                    status TEXT NOT NULL,
                    station_id TEXT NOT NULL,
                    call TEXT NOT NULL,
                    reviewed_utc TEXT NOT NULL,
                    UNIQUE(user_id, location_id, band, frequency)
                );
                CREATE TABLE IF NOT EXISTS announcements (
                    announcement_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    published_utc TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS support_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Prepared'
                );
                CREATE TABLE IF NOT EXISTS import_batches (
                    batch_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    source_format TEXT NOT NULL,
                    date_protocol TEXT NOT NULL,
                    time_protocol TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    accepted_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_import_batches_user
                    ON import_batches(user_id, created_utc);
                """
            )
            existing_user_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            for column, definition in {
                "theme_name": "TEXT NOT NULL DEFAULT 'Midnight blue'",
                "large_text": "INTEGER NOT NULL DEFAULT 0",
                "reduce_motion": "INTEGER NOT NULL DEFAULT 0",
                "walkthrough_complete": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if column not in existing_user_columns:
                    connection.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            existing_log_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(logs)").fetchall()
            }
            for column, definition in {
                "updated_utc": "TEXT NOT NULL DEFAULT ''",
                "deleted_utc": "TEXT NOT NULL DEFAULT ''",
                "revision": "INTEGER NOT NULL DEFAULT 1",
            }.items():
                if column not in existing_log_columns:
                    connection.execute(f"ALTER TABLE logs ADD COLUMN {column} {definition}")
            legacy_nwr_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT station_id FROM logs WHERE band='NWR' AND deleted_utc=''"
                ).fetchall()
            ]
            if legacy_nwr_ids:
                from dxcore.stations import load_stations

                nwr = load_stations()
                canonical_counties = nwr[nwr["band"] == "NWR"].set_index("station_id")["county"].to_dict()
                connection.executemany(
                    "UPDATE logs SET station_county=? WHERE band='NWR' AND station_id=?",
                    [(canonical_counties.get(station_id, ""), station_id) for station_id in legacy_nwr_ids],
                )
            count = connection.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
            if count == 0:
                connection.execute(
                    "INSERT INTO announcements VALUES (?, ?, ?, ?, 1)",
                    (
                        "welcome-s7",
                        "Season 7 staging is underway",
                        "Complete a band baseline, then use the reviewed log-entry workflow. Test data stays local until Google writes are explicitly enabled.",
                        iso_utc(),
                    ),
                )

    def upsert_user(self, user_id: str, email: str, display_name: str) -> None:
        now = iso_utc()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users(user_id, email, display_name, created_utc, updated_utc)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    email=excluded.email,
                    display_name=CASE
                        WHEN TRIM(users.display_name)='' THEN excluded.display_name
                        ELSE users.display_name
                    END,
                    updated_utc=excluded.updated_utc
                """,
                (user_id, email, display_name, now, now),
            )

    def user_profile(self, user_id: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row is not None else None

    def users(self) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                "SELECT user_id, email, display_name FROM users ORDER BY display_name", connection
            )

    def sheet_rows(self, sheet_name: str) -> list[dict[str, object]]:
        if sheet_name not in SHEET_TABLES:
            return []
        table = SHEET_TABLES[sheet_name]
        columns = SHEET_SCHEMAS[sheet_name]
        with self.connect() as connection:
            frame = pd.read_sql_query(
                f"SELECT {','.join(columns)} FROM \"{table}\"",
                connection,
            )
        return frame.where(pd.notna(frame), "").to_dict("records")

    def sheet_row(self, sheet_name: str, row_id: str) -> dict[str, object] | None:
        if sheet_name not in SHEET_TABLES:
            return None
        table = SHEET_TABLES[sheet_name]
        columns = SHEET_SCHEMAS[sheet_name]
        key_column = columns[0]
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT {','.join(columns)} FROM \"{table}\" WHERE {key_column}=?",
                (row_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def merge_sheet_rows(self, sheet_name: str, rows: list[dict[str, object]]) -> None:
        if sheet_name not in SHEET_TABLES or not rows:
            return
        table = SHEET_TABLES[sheet_name]
        columns = SHEET_SCHEMAS[sheet_name]
        placeholders = ",".join("?" for _ in columns)
        with self.connect() as connection:
            connection.executemany(
                f"INSERT OR REPLACE INTO \"{table}\"({','.join(columns)}) VALUES ({placeholders})",
                [tuple(row.get(column, "") for column in columns) for row in rows],
            )

    def update_user_preferences(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        theme_name: str | None = None,
        large_text: bool | None = None,
        reduce_motion: bool | None = None,
        walkthrough_complete: bool | None = None,
    ) -> None:
        values: dict[str, object] = {}
        if display_name is not None:
            cleaned = display_name.strip()
            if not cleaned:
                raise ValueError("Display name cannot be blank.")
            values["display_name"] = cleaned[:80]
        if theme_name is not None:
            values["theme_name"] = theme_name
        if large_text is not None:
            values["large_text"] = int(large_text)
        if reduce_motion is not None:
            values["reduce_motion"] = int(reduce_motion)
        if walkthrough_complete is not None:
            values["walkthrough_complete"] = int(walkthrough_complete)
        if not values:
            return
        values["updated_utc"] = iso_utc()
        assignments = ", ".join(f"{column}=?" for column in values)
        with self.connect() as connection:
            result = connection.execute(
                f"UPDATE users SET {assignments} WHERE user_id=?",
                (*values.values(), user_id),
            )
            if result.rowcount != 1:
                raise ValueError("The signed-in profile could not be updated.")

    def create_support_ticket(self, user_id: str, category: str, subject: str, details: str) -> str:
        ticket_id = f"ticket_{uuid.uuid4().hex[:16]}"
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO support_tickets VALUES (?, ?, ?, ?, ?, ?, 'Prepared')",
                (ticket_id, user_id, category, subject, details, iso_utc()),
            )
        return ticket_id

    def add_location(self, user_id: str, values: dict[str, object]) -> str:
        location_id = f"qth_{uuid.uuid4().hex[:16]}"
        is_home = bool(values.get("is_home"))
        with self.connect() as connection:
            if is_home:
                connection.execute("UPDATE locations SET is_home=0 WHERE user_id=?", (user_id,))
            connection.execute(
                """
                INSERT INTO locations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location_id,
                    user_id,
                    str(values.get("label", "New QTH")),
                    str(values.get("city", "")),
                    str(values.get("region", "")),
                    str(values.get("country", "")),
                    str(values.get("grid", "")),
                    float(values["latitude"]),
                    float(values["longitude"]),
                    int(is_home),
                    iso_utc(),
                ),
            )
        return location_id

    def set_home_location(self, user_id: str, location_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE locations SET is_home=0 WHERE user_id=?", (user_id,))
            result = connection.execute(
                "UPDATE locations SET is_home=1 WHERE user_id=? AND location_id=?", (user_id, location_id)
            )
            if result.rowcount != 1:
                raise ValueError("Location does not belong to the signed-in user.")

    def locations(self, user_id: str) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                "SELECT * FROM locations WHERE user_id=? ORDER BY is_home DESC, created_utc", connection, params=(user_id,)
            )

    def all_locations(self) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query("SELECT * FROM locations", connection)

    def location_usage(self, user_id: str, location_id: str) -> dict[str, int]:
        with self.connect() as connection:
            logs = connection.execute(
                "SELECT COUNT(*) FROM logs WHERE user_id=? AND location_id=? AND deleted_utc=''",
                (user_id, location_id),
            ).fetchone()[0]
            bandscan = connection.execute(
                "SELECT COUNT(*) FROM bandscan WHERE user_id=? AND location_id=?",
                (user_id, location_id),
            ).fetchone()[0]
        return {"logs": int(logs), "bandscan": int(bandscan)}

    def delete_location(self, user_id: str, location_id: str) -> tuple[bool, str]:
        with self.connect() as connection:
            location = connection.execute(
                "SELECT is_home FROM locations WHERE user_id=? AND location_id=?",
                (user_id, location_id),
            ).fetchone()
            if location is None:
                return False, "Location does not belong to the signed-in user."
            log_count = connection.execute(
                "SELECT COUNT(*) FROM logs WHERE user_id=? AND location_id=? AND deleted_utc=''",
                (user_id, location_id),
            ).fetchone()[0]
            if log_count:
                return False, f"This location is locked because {log_count:,} active log(s) use it."
            scan_count = connection.execute(
                "SELECT COUNT(*) FROM bandscan WHERE user_id=? AND location_id=?",
                (user_id, location_id),
            ).fetchone()[0]
            if scan_count:
                return False, f"This location is locked because {scan_count:,} bandscan result(s) use it."
            if location["is_home"]:
                alternatives = connection.execute(
                    "SELECT COUNT(*) FROM locations WHERE user_id=? AND location_id<>?",
                    (user_id, location_id),
                ).fetchone()[0]
                if alternatives:
                    return False, "Choose another Home QTH before deleting this one."
            connection.execute(
                "DELETE FROM locations WHERE user_id=? AND location_id=?", (user_id, location_id)
            )
        return True, "Location deleted."

    def save_bandscan(
        self,
        user_id: str,
        location_id: str,
        band: str,
        frequency: float,
        status: str,
        station_id: str = "",
        call: str = "",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO bandscan VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, location_id, band, frequency) DO UPDATE SET
                    status=excluded.status,
                    station_id=excluded.station_id,
                    call=excluded.call,
                    reviewed_utc=excluded.reviewed_utc
                """,
                (
                    f"scan_{uuid.uuid4().hex[:16]}",
                    user_id,
                    location_id,
                    band,
                    float(frequency),
                    status,
                    station_id,
                    call,
                    iso_utc(),
                ),
            )

    def fill_bandscan_open(
        self, user_id: str, location_id: str, band: str, frequencies: list[float]
    ) -> None:
        now = iso_utc()
        with self.connect() as connection:
            for frequency in frequencies:
                connection.execute(
                    """
                    INSERT INTO bandscan VALUES (?, ?, ?, ?, ?, 'OPEN', '', 'OPEN', ?)
                    ON CONFLICT(user_id, location_id, band, frequency) DO NOTHING
                    """,
                    (
                        f"scan_{uuid.uuid4().hex[:16]}",
                        user_id,
                        location_id,
                        band,
                        float(frequency),
                        now,
                    ),
                )

    def bandscan(self, user_id: str, location_id: str, band: str) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                "SELECT * FROM bandscan WHERE user_id=? AND location_id=? AND band=? ORDER BY frequency",
                connection,
                params=(user_id, location_id, band),
            )

    def append_log(self, values: dict[str, object]) -> tuple[bool, str]:
        with self.connect() as connection:
            return self._append_log(connection, values)

    def _append_log(
        self, connection: sqlite3.Connection, values: dict[str, object]
    ) -> tuple[bool, str]:
        reception = datetime.fromisoformat(str(values["reception_utc"]).replace("Z", "+00:00"))
        if reception.tzinfo is None:
            reception = reception.replace(tzinfo=timezone.utc)
        lower = iso_utc(reception - timedelta(minutes=5))
        upper = iso_utc(reception + timedelta(minutes=5))
        duplicate = connection.execute(
            """
            SELECT log_id, reception_utc FROM logs
            WHERE user_id=? AND location_id=? AND station_id=?
              AND deleted_utc=''
              AND reception_utc BETWEEN ? AND ?
            ORDER BY reception_utc LIMIT 1
            """,
            (
                values["user_id"],
                values["location_id"],
                values["station_id"],
                lower,
                upper,
            ),
        ).fetchone()
        if duplicate:
            return False, f"Already logged within five minutes ({duplicate['reception_utc']})."

        log_id = f"log_{uuid.uuid4().hex[:20]}"
        columns = [
            "log_id", "user_id", "location_id", "station_id", "band", "frequency", "call",
            "station_city", "station_region", "station_country", "station_county", "station_grid",
            "station_latitude", "station_longitude", "reception_utc", "distance_miles", "propagation",
            "is_sdr", "is_portable", "notes", "source", "import_batch_id", "created_utc",
            "updated_utc", "deleted_utc", "revision",
        ]
        now = iso_utc()
        payload = {
            "log_id": log_id,
            "created_utc": now,
            "updated_utc": now,
            "deleted_utc": "",
            "revision": 1,
            "import_batch_id": "",
            "notes": "",
            "source": "manual",
            "is_sdr": 0,
            "is_portable": 0,
            **values,
            "reception_utc": iso_utc(reception),
        }
        connection.execute(
            f"INSERT INTO logs({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(payload.get(column, "") for column in columns),
        )
        return True, log_id

    def append_logs(self, rows: list[dict[str, object]]) -> dict[str, object]:
        accepted_ids: list[str] = []
        rejected: list[str] = []
        with self.connect() as connection:
            for values in rows:
                accepted, message = self._append_log(connection, values)
                if accepted:
                    accepted_ids.append(message)
                else:
                    rejected.append(message)
        return {
            "accepted": len(accepted_ids),
            "rejected": len(rejected),
            "log_ids": accepted_ids,
            "messages": rejected,
        }

    def record_import_batch(
        self,
        *,
        batch_id: str,
        user_id: str,
        filename: str,
        source_format: str,
        date_protocol: str,
        time_protocol: str,
        timezone_name: str,
        row_count: int,
        accepted_count: int,
        status: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO import_batches(
                    batch_id, user_id, filename, source_format, date_protocol,
                    time_protocol, timezone, row_count, accepted_count, status, created_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    user_id,
                    filename,
                    source_format,
                    date_protocol,
                    time_protocol,
                    timezone_name,
                    int(row_count),
                    int(accepted_count),
                    status,
                    iso_utc(),
                ),
            )

    def update_log(self, user_id: str, log_id: str, values: dict[str, object]) -> tuple[bool, str]:
        allowed = {
            "reception_utc", "propagation", "is_sdr", "is_portable", "notes",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return False, "No editable fields were supplied."
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM logs WHERE user_id=? AND log_id=? AND deleted_utc=''",
                (user_id, log_id),
            ).fetchone()
            if existing is None:
                return False, "Reception was not found or does not belong to the signed-in user."
            reception = datetime.fromisoformat(
                str(updates.get("reception_utc", existing["reception_utc"])).replace("Z", "+00:00")
            )
            if reception.tzinfo is None:
                reception = reception.replace(tzinfo=timezone.utc)
            reception_iso = iso_utc(reception)
            duplicate = connection.execute(
                """
                SELECT log_id, reception_utc FROM logs
                WHERE user_id=? AND location_id=? AND station_id=?
                  AND log_id<>? AND deleted_utc=''
                  AND reception_utc BETWEEN ? AND ?
                ORDER BY reception_utc LIMIT 1
                """,
                (
                    user_id,
                    existing["location_id"],
                    existing["station_id"],
                    log_id,
                    iso_utc(reception - timedelta(minutes=5)),
                    iso_utc(reception + timedelta(minutes=5)),
                ),
            ).fetchone()
            if duplicate:
                return False, f"That change would duplicate a log within five minutes ({duplicate['reception_utc']})."
            updates["reception_utc"] = reception_iso
            updates["updated_utc"] = iso_utc()
            assignments = ", ".join(f"{column}=?" for column in updates)
            connection.execute(
                f"UPDATE logs SET {assignments}, revision=revision+1 WHERE user_id=? AND log_id=?",
                (*updates.values(), user_id, log_id),
            )
        return True, "Reception updated."

    def delete_log(self, user_id: str, log_id: str) -> tuple[bool, str]:
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE logs
                SET deleted_utc=?, updated_utc=?, revision=revision+1
                WHERE user_id=? AND log_id=? AND deleted_utc=''
                """,
                (iso_utc(), iso_utc(), user_id, log_id),
            )
            if result.rowcount != 1:
                return False, "Reception was not found or does not belong to the signed-in user."
        return True, "Reception deleted."

    def logs(self, user_id: str | None = None) -> pd.DataFrame:
        with self.connect() as connection:
            if user_id:
                return pd.read_sql_query(
                    "SELECT * FROM logs WHERE user_id=? AND deleted_utc='' ORDER BY reception_utc DESC", connection, params=(user_id,)
                )
            return pd.read_sql_query("SELECT * FROM logs WHERE deleted_utc='' ORDER BY reception_utc DESC", connection)

    def announcements(self) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                "SELECT * FROM announcements WHERE active=1 ORDER BY published_utc DESC", connection
            )
