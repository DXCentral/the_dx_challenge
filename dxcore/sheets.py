from __future__ import annotations

import logging
import re
import threading
from datetime import date, datetime
from typing import Any

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from dxcore.schema import SHEET_SCHEMAS
from dxcore.store import LocalStore, SHEET_TABLES


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LOGGER = logging.getLogger(__name__)


def _cell(value: object) -> object:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


class GoogleSheetMirror:
    """Small, explicit Google Sheets mirror for the app's durable records."""

    def __init__(self, service_account_info: dict[str, object], spreadsheet_id: str) -> None:
        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        self.client = gspread.authorize(credentials)
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)
        self._worksheets: dict[str, Any] = {}
        self._lock = threading.RLock()

    def _worksheet(self, sheet_name: str):
        with self._lock:
            if sheet_name in self._worksheets:
                return self._worksheets[sheet_name]
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                worksheet = self.spreadsheet.add_worksheet(
                    title=sheet_name,
                    rows=1000,
                    cols=max(10, len(SHEET_SCHEMAS[sheet_name])),
                )
            self._ensure_header(worksheet, sheet_name)
            self._worksheets[sheet_name] = worksheet
            return worksheet

    def _ensure_header(self, worksheet, sheet_name: str) -> None:
        expected = SHEET_SCHEMAS[sheet_name]
        values = worksheet.get_all_values()
        if not values:
            worksheet.update(range_name="A1", values=[expected])
            return
        current = [str(value).strip() for value in values[0]]
        if current == expected:
            return
        # Preserve rows by field name while migrating a managed tab's schema.
        records = [
            dict(zip(current, row + [""] * max(0, len(current) - len(row)), strict=False))
            for row in values[1:]
            if any(str(value).strip() for value in row)
        ]
        remapped = [expected] + [
            [_cell(record.get(column, "")) for column in expected] for record in records
        ]
        worksheet.clear()
        worksheet.update(range_name="A1", values=remapped)

    def rows(self, sheet_name: str) -> list[dict[str, object]]:
        worksheet = self._worksheet(sheet_name)
        values = worksheet.get_all_values()
        if len(values) < 2:
            return []
        headers = SHEET_SCHEMAS[sheet_name]
        return [
            dict(zip(headers, row + [""] * max(0, len(headers) - len(row)), strict=False))
            for row in values[1:]
            if any(str(value).strip() for value in row)
        ]

    def upsert_rows(self, sheet_name: str, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        with self._lock:
            worksheet = self._worksheet(sheet_name)
            columns = SHEET_SCHEMAS[sheet_name]
            key = columns[0]
            existing_ids = worksheet.col_values(1)
            row_numbers = {
                str(value): index
                for index, value in enumerate(existing_ids[1:], start=2)
                if str(value)
            }
            additions: list[list[object]] = []
            for record in rows:
                row_id = str(record.get(key, "")).strip()
                if not row_id:
                    continue
                values = [_cell(record.get(column, "")) for column in columns]
                if row_id in row_numbers:
                    worksheet.update(
                        range_name=f"A{row_numbers[row_id]}",
                        values=[values],
                        value_input_option="RAW",
                    )
                else:
                    additions.append(values)
            if additions:
                worksheet.append_rows(additions, value_input_option="RAW")

    def delete_row(self, sheet_name: str, row_id: str) -> None:
        worksheet = self._worksheet(sheet_name)
        try:
            match = worksheet.find(
                re.compile(f"^{re.escape(str(row_id))}$"), in_column=1
            )
        except gspread.CellNotFound:
            return
        if match is not None and match.row > 1:
            worksheet.delete_rows(match.row)

    def bootstrap(self, local: LocalStore) -> None:
        # Remote data wins when present. A brand-new managed tab is seeded from
        # the current local cache so a deployment upgrade does not discard the
        # owner's existing staging records.
        for sheet_name in SHEET_TABLES:
            remote_rows = self.rows(sheet_name)
            if remote_rows:
                local.merge_sheet_rows(sheet_name, remote_rows)
            else:
                self.upsert_rows(sheet_name, local.sheet_rows(sheet_name))


class HybridStore:
    """Fast local reads plus guarded, durable Google Sheet writes."""

    def __init__(self, local: LocalStore, mirror: GoogleSheetMirror) -> None:
        self.local = local
        self.mirror = mirror
        self.sync_error = ""
        self._pending_sync: dict[str, set[str]] = {}
        try:
            self.mirror.bootstrap(self.local)
        except Exception as error:  # The UI reports degraded persistence.
            LOGGER.exception("Google Sheet bootstrap failed")
            self.sync_error = f"{type(error).__name__}: {error}"

    def __getattr__(self, name: str):
        return getattr(self.local, name)

    @property
    def sync_enabled(self) -> bool:
        return True

    @property
    def pending_sync_count(self) -> int:
        return sum(len(row_ids) for row_ids in self._pending_sync.values())

    def _sync(self, sheet_name: str, rows: list[dict[str, object]]) -> None:
        key = SHEET_SCHEMAS[sheet_name][0]
        row_ids = {
            str(row.get(key, "")).strip()
            for row in rows
            if str(row.get(key, "")).strip()
        }
        try:
            self.mirror.upsert_rows(sheet_name, rows)
            pending = self._pending_sync.get(sheet_name, set())
            pending.difference_update(row_ids)
            if not pending:
                self._pending_sync.pop(sheet_name, None)
            self.sync_error = "" if not self.pending_sync_count else "Changes are waiting to be resynced."
        except Exception as error:
            LOGGER.exception("Google Sheet write failed for %s", sheet_name)
            self._pending_sync.setdefault(sheet_name, set()).update(row_ids)
            self.sync_error = f"{type(error).__name__}: {error}"

    def retry_sync(self) -> tuple[bool, str]:
        """Retry only records retained after failed writes, plus a small health check."""
        try:
            if not self._pending_sync:
                self.mirror.upsert_rows("Users", self.local.sheet_rows("Users"))
            else:
                for sheet_name, row_ids in list(self._pending_sync.items()):
                    rows = [
                        row
                        for row_id in row_ids
                        if (row := self.local.sheet_row(sheet_name, row_id)) is not None
                    ]
                    self.mirror.upsert_rows(sheet_name, rows)
                self._pending_sync.clear()
            self.sync_error = ""
            return True, "Google Sheet sync is durable again."
        except Exception as error:
            LOGGER.exception("Google Sheet retry failed")
            self.sync_error = f"{type(error).__name__}: {error}"
            return False, "Google Sheet sync is still unavailable. Your local cache is unchanged."

    def _sync_one(self, sheet_name: str, row_id: str) -> None:
        row = self.local.sheet_row(sheet_name, row_id)
        if row is not None:
            self._sync(sheet_name, [row])

    def upsert_user(self, user_id: str, email: str, display_name: str) -> None:
        self.local.upsert_user(user_id, email, display_name)
        self._sync_one("Users", user_id)

    def update_user_preferences(self, user_id: str, **values: object) -> None:
        self.local.update_user_preferences(user_id, **values)
        self._sync_one("Users", user_id)

    def create_support_ticket(
        self, user_id: str, category: str, subject: str, details: str
    ) -> str:
        ticket_id = self.local.create_support_ticket(user_id, category, subject, details)
        self._sync_one("Support Tickets", ticket_id)
        return ticket_id

    def update_support_ticket(
        self, ticket_id: str, *, status: str, admin_comment: str
    ) -> tuple[bool, str]:
        updated, message = self.local.update_support_ticket(
            ticket_id, status=status, admin_comment=admin_comment
        )
        if updated:
            self._sync_one("Support Tickets", ticket_id)
        return updated, message

    def add_location(self, user_id: str, values: dict[str, object]) -> str:
        location_id = self.local.add_location(user_id, values)
        self._sync("Locations", self.local.locations(user_id).to_dict("records"))
        return location_id

    def set_home_location(self, user_id: str, location_id: str) -> None:
        self.local.set_home_location(user_id, location_id)
        self._sync("Locations", self.local.locations(user_id).to_dict("records"))

    def update_location_geography(
        self,
        user_id: str,
        location_id: str,
        *,
        grid: str,
        latitude: float,
        longitude: float,
    ) -> tuple[bool, str]:
        updated, message = self.local.update_location_geography(
            user_id,
            location_id,
            grid=grid,
            latitude=latitude,
            longitude=longitude,
        )
        if updated:
            self._sync_one("Locations", location_id)
        return updated, message

    def delete_location(self, user_id: str, location_id: str) -> tuple[bool, str]:
        deleted, message = self.local.delete_location(user_id, location_id)
        if deleted:
            try:
                self.mirror.delete_row("Locations", location_id)
                self.sync_error = ""
            except Exception as error:
                LOGGER.exception("Google Sheet location delete failed")
                self.sync_error = f"{type(error).__name__}: {error}"
        return deleted, message

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
        self.local.save_bandscan(
            user_id, location_id, band, frequency, status, station_id, call
        )
        rows = self.local.bandscan(user_id, location_id, band)
        selected = rows[(rows["frequency"].astype(float) - float(frequency)).abs() < 0.001]
        self._sync("Bandscan", selected.to_dict("records"))

    def fill_bandscan_open(
        self, user_id: str, location_id: str, band: str, frequencies: list[float]
    ) -> None:
        self.local.fill_bandscan_open(user_id, location_id, band, frequencies)
        self._sync(
            "Bandscan", self.local.bandscan(user_id, location_id, band).to_dict("records")
        )

    def append_log(self, values: dict[str, object]) -> tuple[bool, str]:
        accepted, message = self.local.append_log(values)
        if accepted:
            self._sync_one("Logging Entries", message)
        return accepted, message

    def append_logs(self, rows: list[dict[str, object]]) -> dict[str, object]:
        result = self.local.append_logs(rows)
        self._sync(
            "Logging Entries",
            [
                record
                for log_id in result["log_ids"]
                if (record := self.local.sheet_row("Logging Entries", str(log_id))) is not None
            ],
        )
        return result

    def update_log(
        self, user_id: str, log_id: str, values: dict[str, object]
    ) -> tuple[bool, str]:
        updated, message = self.local.update_log(user_id, log_id, values)
        if updated:
            self._sync_one("Logging Entries", log_id)
        return updated, message

    def admin_update_log(
        self, log_id: str, values: dict[str, object]
    ) -> tuple[bool, str]:
        updated, message = self.local.admin_update_log(log_id, values)
        if updated:
            self._sync_one("Logging Entries", log_id)
        return updated, message

    def delete_log(self, user_id: str, log_id: str) -> tuple[bool, str]:
        deleted, message = self.local.delete_log(user_id, log_id)
        if deleted:
            self._sync_one("Logging Entries", log_id)
        return deleted, message

    def update_station_review_status(
        self, log_id: str, status: str
    ) -> tuple[bool, str]:
        updated, message = self.local.update_station_review_status(log_id, status)
        if updated:
            self._sync_one("Logging Entries", log_id)
        return updated, message

    def set_shoutout_read(self, entry_id: str, read_on_air: bool) -> tuple[bool, str]:
        updated, message = self.local.set_shoutout_read(entry_id, read_on_air)
        if updated:
            self._sync_one("Shoutout Status", entry_id)
        return updated, message

    def promote_station_override(
        self, log_id: str
    ) -> tuple[bool, str, str]:
        promoted, message, station_id = self.local.promote_station_override(log_id)
        if promoted:
            self._sync_one("Station Overrides", station_id)
            related = self.local.logs()
            related = related[related["station_id"].astype(str) == station_id]
            self._sync("Logging Entries", related.to_dict("records"))
        return promoted, message, station_id

    def record_import_batch(self, **values: object) -> None:
        self.local.record_import_batch(**values)
        self._sync_one("Import Batches", str(values["batch_id"]))

    def upsert_announcement(self, values: dict[str, object]) -> str:
        announcement_id = self.local.upsert_announcement(values)
        self._sync_one("Announcements", announcement_id)
        return announcement_id

    def delete_announcement(self, announcement_id: str) -> tuple[bool, str]:
        deleted, message = self.local.delete_announcement(announcement_id)
        if deleted:
            try:
                self.mirror.delete_row("Announcements", announcement_id)
                self.sync_error = ""
            except Exception as error:
                LOGGER.exception("Google Sheet announcement delete failed")
                self.sync_error = f"{type(error).__name__}: {error}"
        return deleted, message

    def upsert_challenge(self, values: dict[str, object]) -> str:
        challenge_id = self.local.upsert_challenge(values)
        self._sync_one("Challenges", challenge_id)
        return challenge_id

    def delete_challenge(self, challenge_id: str) -> tuple[bool, str]:
        deleted, message = self.local.delete_challenge(challenge_id)
        if deleted:
            try:
                self.mirror.delete_row("Challenges", challenge_id)
                self.sync_error = ""
            except Exception as error:
                LOGGER.exception("Google Sheet challenge delete failed")
                self.sync_error = f"{type(error).__name__}: {error}"
        return deleted, message
