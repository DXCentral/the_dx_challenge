from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

from dxcore.config import CONTENT_DIR, LOCAL_DB_PATH
from dxcore.geo import haversine_miles, latlon_to_grid, valid_coordinates, valid_grid
from dxcore.schema import SHEET_SCHEMAS


SHEET_TABLES = {
    "Users": "users",
    "Locations": "locations",
    "Logging Entries": "logs",
    "Bandscan": "bandscan",
    "Import Batches": "import_batches",
    "Station Overrides": "station_overrides",
    "Announcements": "announcements",
    "Challenges": "challenges",
    "Support Tickets": "support_tickets",
    "Shoutout Status": "shoutout_status",
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
                    station_review_status TEXT NOT NULL DEFAULT '',
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
                    start_utc TEXT NOT NULL DEFAULT '',
                    end_utc TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    published_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS challenges (
                    challenge_id TEXT PRIMARY KEY,
                    challenge_type TEXT NOT NULL,
                    challenge_name TEXT NOT NULL,
                    timeframe_tag TEXT NOT NULL,
                    start_utc TEXT NOT NULL,
                    end_utc TEXT NOT NULL,
                    bands TEXT NOT NULL,
                    frequencies TEXT NOT NULL,
                    include_countries TEXT NOT NULL,
                    exclude_countries TEXT NOT NULL,
                    include_regions TEXT NOT NULL,
                    exclude_regions TEXT NOT NULL,
                    propagation_modes TEXT NOT NULL,
                    dayparts TEXT NOT NULL,
                    min_distance TEXT NOT NULL,
                    max_distance TEXT NOT NULL,
                    scoring_method TEXT NOT NULL,
                    description TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS support_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Open',
                    admin_comment TEXT NOT NULL DEFAULT ''
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
                CREATE TABLE IF NOT EXISTS station_overrides (
                    station_id TEXT PRIMARY KEY,
                    band TEXT NOT NULL,
                    frequency REAL NOT NULL,
                    call TEXT NOT NULL,
                    city TEXT NOT NULL,
                    region TEXT NOT NULL,
                    country TEXT NOT NULL,
                    county TEXT NOT NULL,
                    grid TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    source_log_id TEXT NOT NULL,
                    approved_utc TEXT NOT NULL,
                    updated_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS shoutout_status (
                    entry_id TEXT PRIMARY KEY,
                    read_on_air INTEGER NOT NULL DEFAULT 0,
                    read_utc TEXT NOT NULL DEFAULT '',
                    updated_utc TEXT NOT NULL
                );
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
                "station_review_status": "TEXT NOT NULL DEFAULT ''",
                "updated_utc": "TEXT NOT NULL DEFAULT ''",
                "deleted_utc": "TEXT NOT NULL DEFAULT ''",
                "revision": "INTEGER NOT NULL DEFAULT 1",
            }.items():
                if column not in existing_log_columns:
                    connection.execute(f"ALTER TABLE logs ADD COLUMN {column} {definition}")
            existing_announcement_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(announcements)").fetchall()
            }
            for column, definition in {
                "start_utc": "TEXT NOT NULL DEFAULT ''",
                "end_utc": "TEXT NOT NULL DEFAULT ''",
                "updated_utc": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if column not in existing_announcement_columns:
                    connection.execute(
                        f"ALTER TABLE announcements ADD COLUMN {column} {definition}"
                    )
            existing_ticket_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(support_tickets)").fetchall()
            }
            for column, definition in {
                "updated_utc": "TEXT NOT NULL DEFAULT ''",
                "admin_comment": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if column not in existing_ticket_columns:
                    connection.execute(
                        f"ALTER TABLE support_tickets ADD COLUMN {column} {definition}"
                    )
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
            self._seed_content(connection)

    def _seed_content(self, connection: sqlite3.Connection) -> None:
        now = iso_utc()
        if connection.execute("SELECT COUNT(*) FROM announcements").fetchone()[0] == 0:
            path = CONTENT_DIR / "announcements.csv"
            if path.exists():
                rows = pd.read_csv(path, dtype=str).fillna("").to_dict("records")
                connection.executemany(
                    """
                    INSERT INTO announcements(
                        announcement_id,title,body,start_utc,end_utc,active,published_utc,updated_utc
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            row.get("announcement_id", ""),
                            row.get("title", ""),
                            row.get("body", row.get("message", "")),
                            row.get("start_utc", ""),
                            row.get("end_utc", ""),
                            int(str(row.get("active", "true")).lower() not in {"", "0", "false", "no"}),
                            row.get("start_utc", "") or now,
                            now,
                        )
                        for row in rows
                        if row.get("announcement_id")
                    ],
                )
        if connection.execute("SELECT COUNT(*) FROM challenges").fetchone()[0] == 0:
            path = CONTENT_DIR / "challenge_schedule.csv"
            if path.exists():
                rows = pd.read_csv(path, dtype=str).fillna("").to_dict("records")
                columns = SHEET_SCHEMAS["Challenges"]
                values = []
                for row in rows:
                    if not row.get("challenge_id"):
                        continue
                    record = {column: row.get(column, "") for column in columns}
                    record["active"] = int(
                        str(row.get("active", "true")).lower()
                        not in {"", "0", "false", "no"}
                    )
                    record["scoring_method"] = row.get("scoring_method", "") or "Unique stations"
                    record["created_utc"] = now
                    record["updated_utc"] = now
                    values.append(tuple(record[column] for column in columns))
                connection.executemany(
                    f"INSERT INTO challenges({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    values,
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
        now = iso_utc()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO support_tickets(
                    ticket_id,user_id,category,subject,details,created_utc,
                    updated_utc,status,admin_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Open', '')
                """,
                (ticket_id, user_id, category, subject, details, now, now),
            )
        return ticket_id

    def support_tickets(self, user_id: str | None = None) -> pd.DataFrame:
        with self.connect() as connection:
            if user_id:
                return pd.read_sql_query(
                    "SELECT * FROM support_tickets WHERE user_id=? ORDER BY updated_utc DESC, created_utc DESC",
                    connection,
                    params=(user_id,),
                )
            return pd.read_sql_query(
                "SELECT * FROM support_tickets ORDER BY updated_utc DESC, created_utc DESC",
                connection,
            )

    def update_support_ticket(
        self, ticket_id: str, *, status: str, admin_comment: str
    ) -> tuple[bool, str]:
        allowed = {"Open", "In progress", "Waiting on DXer", "Resolved", "Closed"}
        if status not in allowed:
            return False, "Invalid support-ticket status."
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE support_tickets
                SET status=?, admin_comment=?, updated_utc=?
                WHERE ticket_id=?
                """,
                (status, admin_comment.strip()[:4000], iso_utc(), ticket_id),
            )
        return (True, "Support ticket updated.") if result.rowcount == 1 else (
            False,
            "Support ticket was not found.",
        )

    def add_location(self, user_id: str, values: dict[str, object]) -> str:
        location_id = f"qth_{uuid.uuid4().hex[:16]}"
        is_home = bool(values.get("is_home"))
        latitude = values.get("latitude", "")
        longitude = values.get("longitude", "")
        if not valid_coordinates(latitude, longitude):
            raise ValueError("A receiving location requires valid latitude and longitude coordinates.")
        latitude = float(latitude)
        longitude = float(longitude)
        supplied_grid = str(values.get("grid", "")).strip().upper()
        grid = supplied_grid if valid_grid(supplied_grid) else latlon_to_grid(latitude, longitude)
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
                    grid,
                    latitude,
                    longitude,
                    int(is_home),
                    iso_utc(),
                ),
            )
        return location_id

    def update_location_geography(
        self,
        user_id: str,
        location_id: str,
        *,
        grid: str,
        latitude: float,
        longitude: float,
    ) -> tuple[bool, str]:
        if not valid_coordinates(latitude, longitude):
            return False, "The repaired coordinates are invalid."
        supplied_grid = str(grid).strip().upper()
        cleaned_grid = supplied_grid if valid_grid(supplied_grid) else latlon_to_grid(latitude, longitude)
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE locations SET grid=?, latitude=?, longitude=?
                WHERE user_id=? AND location_id=?
                """,
                (cleaned_grid, float(latitude), float(longitude), user_id, location_id),
            )
        return (True, "Location coordinates and grid updated.") if result.rowcount == 1 else (
            False,
            "The receiving location was not found.",
        )

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
            if location["is_home"]:
                alternatives = connection.execute(
                    "SELECT COUNT(*) FROM locations WHERE user_id=? AND location_id<>?",
                    (user_id, location_id),
                ).fetchone()[0]
                if alternatives:
                    return False, "Choose another Home QTH before deleting this one."
            connection.execute(
                "DELETE FROM bandscan WHERE user_id=? AND location_id=?", (user_id, location_id)
            )
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
            "is_sdr", "is_portable", "notes", "source", "station_review_status",
            "import_batch_id", "created_utc",
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
            "station_review_status": "",
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

    def admin_update_log(
        self, log_id: str, values: dict[str, object]
    ) -> tuple[bool, str]:
        """Edit a reviewed reception without changing its owner or provenance."""
        allowed = {
            "station_id", "band", "frequency", "call", "station_city",
            "station_region", "station_country", "station_county", "station_grid",
            "station_latitude", "station_longitude", "reception_utc", "propagation",
            "is_sdr", "is_portable", "notes",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return False, "No editable fields were supplied."
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM logs WHERE log_id=? AND deleted_utc=''", (log_id,)
            ).fetchone()
            if existing is None:
                return False, "Reception was not found."
            merged = {**dict(existing), **updates}
            required = ["station_id", "band", "call", "station_city", "station_country"]
            if any(not str(merged.get(field, "")).strip() for field in required):
                return False, "Station ID, band, call/name, city, and country are required."
            try:
                merged["frequency"] = float(merged["frequency"])
                reception = datetime.fromisoformat(
                    str(merged["reception_utc"]).replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                return False, "Frequency and reception UTC must be valid."
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
                    existing["user_id"], existing["location_id"], merged["station_id"],
                    log_id, iso_utc(reception - timedelta(minutes=5)),
                    iso_utc(reception + timedelta(minutes=5)),
                ),
            ).fetchone()
            if duplicate:
                return False, f"That change would duplicate a log within five minutes ({duplicate['reception_utc']})."

            latitude = merged.get("station_latitude", "")
            longitude = merged.get("station_longitude", "")
            if valid_coordinates(latitude, longitude):
                latitude = float(latitude)
                longitude = float(longitude)
                merged["station_latitude"] = latitude
                merged["station_longitude"] = longitude
                if not valid_grid(str(merged.get("station_grid", ""))):
                    merged["station_grid"] = latlon_to_grid(latitude, longitude)
                qth = connection.execute(
                    "SELECT latitude, longitude FROM locations WHERE location_id=?",
                    (existing["location_id"],),
                ).fetchone()
                if qth is not None:
                    merged["distance_miles"] = round(
                        haversine_miles(
                            float(qth["latitude"]), float(qth["longitude"]), latitude, longitude
                        ),
                        1,
                    )
            merged["reception_utc"] = reception_iso
            updates = {key: merged[key] for key in allowed if key in merged}
            if "distance_miles" in merged:
                updates["distance_miles"] = merged["distance_miles"]
            updates["updated_utc"] = iso_utc()
            assignments = ", ".join(f"{column}=?" for column in updates)
            connection.execute(
                f"UPDATE logs SET {assignments}, revision=revision+1 WHERE log_id=?",
                (*updates.values(), log_id),
            )
        return True, "Reception updated by the administrator."

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

    def shoutout_statuses(self) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                "SELECT * FROM shoutout_status ORDER BY updated_utc DESC", connection
            )

    def set_shoutout_read(self, entry_id: str, read_on_air: bool) -> tuple[bool, str]:
        cleaned_id = str(entry_id).strip()
        if not cleaned_id:
            return False, "The shoutout entry ID is missing."
        now = iso_utc()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO shoutout_status(entry_id, read_on_air, read_utc, updated_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                    read_on_air=excluded.read_on_air,
                    read_utc=excluded.read_utc,
                    updated_utc=excluded.updated_utc
                """,
                (cleaned_id, int(read_on_air), now if read_on_air else "", now),
            )
        return True, "Shoutout marked as read on air." if read_on_air else "Read-on-air mark removed."

    def station_review_logs(self) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                """
                SELECT * FROM logs
                WHERE deleted_utc=''
                  AND station_review_status IN ('Pending', 'Needs database addition')
                ORDER BY reception_utc ASC, updated_utc ASC
                """,
                connection,
            )

    def station_overrides(self) -> pd.DataFrame:
        with self.connect() as connection:
            return pd.read_sql_query(
                "SELECT * FROM station_overrides ORDER BY band, frequency, call",
                connection,
            )

    def promote_station_override(
        self, log_id: str
    ) -> tuple[bool, str, str]:
        """Promote one reviewed unlisted station and resolve its related reports."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM logs WHERE log_id=? AND deleted_utc=''", (log_id,)
            ).fetchone()
            if row is None:
                return False, "Reception was not found.", ""
            required = [row["station_id"], row["band"], row["call"], row["station_city"], row["station_country"]]
            if any(not str(value).strip() for value in required):
                return False, "Complete the station ID, band, call/name, city, and country first.", ""
            if not valid_coordinates(row["station_latitude"], row["station_longitude"]):
                return False, "Add valid station latitude and longitude before promoting this station.", ""
            latitude = float(row["station_latitude"])
            longitude = float(row["station_longitude"])
            grid = str(row["station_grid"]).strip().upper()
            if not valid_grid(grid):
                grid = latlon_to_grid(latitude, longitude)
            now = iso_utc()
            existing = connection.execute(
                "SELECT approved_utc FROM station_overrides WHERE station_id=?",
                (row["station_id"],),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO station_overrides(
                    station_id,band,frequency,call,city,region,country,county,grid,
                    latitude,longitude,source_log_id,approved_utc,updated_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(station_id) DO UPDATE SET
                    band=excluded.band, frequency=excluded.frequency, call=excluded.call,
                    city=excluded.city, region=excluded.region, country=excluded.country,
                    county=excluded.county, grid=excluded.grid, latitude=excluded.latitude,
                    longitude=excluded.longitude, source_log_id=excluded.source_log_id,
                    updated_utc=excluded.updated_utc
                """,
                (
                    row["station_id"], row["band"], float(row["frequency"]), row["call"],
                    row["station_city"], row["station_region"], row["station_country"],
                    row["station_county"], grid, latitude, longitude, log_id,
                    existing["approved_utc"] if existing else now, now,
                ),
            )
            resolved = connection.execute(
                """
                UPDATE logs SET station_review_status='Reviewed', updated_utc=?, revision=revision+1
                WHERE station_id=? AND deleted_utc='' AND station_review_status<>''
                """,
                (now, row["station_id"]),
            ).rowcount
        return True, f"Station added to the managed database; {resolved} related review report(s) resolved.", str(row["station_id"])

    def update_station_review_status(
        self, log_id: str, status: str
    ) -> tuple[bool, str]:
        allowed = {"Pending", "Needs database addition", "Reviewed", "Dismissed"}
        if status not in allowed:
            return False, "Invalid station-review status."
        with self.connect() as connection:
            result = connection.execute(
                """
                UPDATE logs
                SET station_review_status=?, updated_utc=?, revision=revision+1
                WHERE log_id=? AND deleted_utc=''
                """,
                (status, iso_utc(), log_id),
            )
        return (True, "Station review updated.") if result.rowcount == 1 else (
            False,
            "Reception was not found.",
        )

    def announcements(self, active_only: bool = False) -> pd.DataFrame:
        with self.connect() as connection:
            where = "WHERE active=1" if active_only else ""
            return pd.read_sql_query(
                f"SELECT * FROM announcements {where} ORDER BY start_utc DESC, published_utc DESC",
                connection,
            )

    def upsert_announcement(self, values: dict[str, object]) -> str:
        announcement_id = str(values.get("announcement_id", "")).strip() or f"announcement_{uuid.uuid4().hex[:12]}"
        title = str(values.get("title", "")).strip()
        body = str(values.get("body", "")).strip()
        if not title or not body:
            raise ValueError("Announcement title and message are required.")
        now = iso_utc()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT published_utc FROM announcements WHERE announcement_id=?",
                (announcement_id,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO announcements(
                    announcement_id,title,body,start_utc,end_utc,active,published_utc,updated_utc
                ) VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(announcement_id) DO UPDATE SET
                    title=excluded.title, body=excluded.body, start_utc=excluded.start_utc,
                    end_utc=excluded.end_utc, active=excluded.active,
                    updated_utc=excluded.updated_utc
                """,
                (
                    announcement_id,
                    title[:160],
                    body[:8000],
                    str(values.get("start_utc", "")),
                    str(values.get("end_utc", "")),
                    int(bool(values.get("active", True))),
                    existing["published_utc"] if existing else now,
                    now,
                ),
            )
        return announcement_id

    def delete_announcement(self, announcement_id: str) -> tuple[bool, str]:
        with self.connect() as connection:
            result = connection.execute(
                "DELETE FROM announcements WHERE announcement_id=?", (announcement_id,)
            )
        return (True, "Announcement deleted.") if result.rowcount == 1 else (
            False,
            "Announcement was not found.",
        )

    def challenges(self, active_only: bool = False) -> pd.DataFrame:
        with self.connect() as connection:
            where = "WHERE active=1" if active_only else ""
            return pd.read_sql_query(
                f"SELECT * FROM challenges {where} ORDER BY start_utc", connection
            )

    def upsert_challenge(self, values: dict[str, object]) -> str:
        challenge_id = str(values.get("challenge_id", "")).strip() or f"challenge_{uuid.uuid4().hex[:12]}"
        name = str(values.get("challenge_name", "")).strip()
        if not name:
            raise ValueError("Challenge name is required.")
        start = datetime.fromisoformat(str(values.get("start_utc", "")).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(values.get("end_utc", "")).replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end <= start:
            raise ValueError("Challenge end must be later than its start.")
        columns = SHEET_SCHEMAS["Challenges"]
        now = iso_utc()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT created_utc FROM challenges WHERE challenge_id=?", (challenge_id,)
            ).fetchone()
            record = {column: str(values.get(column, "")) for column in columns}
            record.update(
                {
                    "challenge_id": challenge_id,
                    "challenge_name": name[:160],
                    "start_utc": iso_utc(start),
                    "end_utc": iso_utc(end),
                    "active": int(bool(values.get("active", True))),
                    "created_utc": existing["created_utc"] if existing else now,
                    "updated_utc": now,
                }
            )
            assignments = ",".join(f"{column}=excluded.{column}" for column in columns[1:])
            connection.execute(
                f"""
                INSERT INTO challenges({','.join(columns)})
                VALUES ({','.join('?' for _ in columns)})
                ON CONFLICT(challenge_id) DO UPDATE SET {assignments}
                """,
                tuple(record[column] for column in columns),
            )
        return challenge_id

    def delete_challenge(self, challenge_id: str) -> tuple[bool, str]:
        with self.connect() as connection:
            result = connection.execute(
                "DELETE FROM challenges WHERE challenge_id=?", (challenge_id,)
            )
        return (True, "Challenge deleted.") if result.rowcount == 1 else (
            False,
            "Challenge was not found.",
        )
