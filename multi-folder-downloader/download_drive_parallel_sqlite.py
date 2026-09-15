#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import queue
import random
import re
import sqlite3
import threading
import time
import urllib.parse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from http import HTTPStatus
from importlib.metadata import version as package_version
from pathlib import Path

import bs4
import gdown
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from gdown.download import _get_session, _sanitize_filename
from gdown.download_folder import _GoogleDriveFile
from gdown.exceptions import DownloadError
from gdown.parse_url import _parse_google_drive_folder_id


DEFAULT_URL = (
    "https://drive.google.com/drive/folders/"
    "18mN48s232REZ1NAcQC9Lkm4uEBQ5yKK3"
)
DEFAULT_OUTPUT = "/home/billy/dev/paczka/PaczkaMerge/00_SOURCES"

SCHEMA_VERSION = "2"

FOLDER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/98.0.4758.102 Safari/537.36"
)

GOOGLE_NATIVE_EXT = {
    _GoogleDriveFile.TYPE_DOCUMENT: ".docx",
    _GoogleDriveFile.TYPE_SPREADSHEET: ".xlsx",
    _GoogleDriveFile.TYPE_PRESENTATION: ".pptx",
}

TERMINAL_FILE_STATUSES = {"done", "skipped", "failed"}


class GracefulStop(Exception):
    """Internal exception used to stop without recording a false failure."""


@dataclass
class RunStats:
    folders_listed_this_run: int = 0
    folders_resumed_without_listing: int = 0
    folders_failed_this_run: int = 0
    folder_retries: int = 0

    files_downloaded_this_run: int = 0
    files_skipped_existing_this_run: int = 0
    files_failed_this_run: int = 0
    file_retries: int = 0

    downloaded_bytes_this_run: int = 0
    skipped_bytes_this_run: int = 0


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def shorten(text: str, limit: int) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    keep = max(8, (limit - 1) // 2)
    return text[:keep] + "…" + text[-keep:]


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def extract_folder_id(url_or_id: str) -> str:
    parsed = _parse_google_drive_folder_id(url=url_or_id)
    if parsed:
        return parsed
    if "/folders/" in url_or_id:
        return (
            url_or_id.split("/folders/", 1)[1]
            .split("?", 1)[0]
            .split("/", 1)[0]
        )
    return url_or_id.strip()


def relative_display(path: Path, output: Path) -> str:
    try:
        rel = path.relative_to(output)
        return "." if str(rel) == "." else str(rel)
    except ValueError:
        return str(path)


def backoff_wait(
    stop_event: threading.Event,
    base: float,
    attempt: int,
) -> None:
    wait = min(base * (2 ** max(0, attempt - 1)), 60.0)
    wait += random.uniform(0.0, min(2.0, wait * 0.20))
    if stop_event.wait(wait):
        raise GracefulStop()


def remove_sqlite_files(path: Path) -> None:
    for candidate in (
        path,
        Path(str(path) + "-wal"),
        Path(str(path) + "-shm"),
    ):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


class Database:
    """
    Persistent traversal/download checkpoint.

    Folder lifecycle:
        pending -> listing -> processing -> done
                    |             |
                    v             v
                  failed        listed  (after interruption)

    'listed' means the Google Drive directory listing is already persisted in
    SQLite and must NOT be fetched again. On resume, a listed folder only
    continues its direct file work.

    File lifecycle:
        pending -> downloading -> done/skipped
                          |
                          v
                       failed

    Interrupted 'downloading' files are reset to pending on the next run.
    """

    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()
        self._schema_lock = threading.Lock()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.path,
                timeout=30,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def close_thread_connection(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            del self._local.conn

    @contextmanager
    def transaction(self):
        """
        Explicit transaction while connections otherwise stay in autocommit
        mode. BEGIN IMMEDIATE serializes the short checkpoint write section,
        while WAL still lets other workers read concurrently.
        """
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    def initialize(
        self,
        *,
        root_id: str,
        output: Path,
    ) -> bool:
        """Return True when a fresh DB was created, False when resuming."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        fresh = not self.path.exists() or self.path.stat().st_size == 0

        with self._schema_lock:
            conn = self._conn()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drive_id TEXT NOT NULL,
                    local_path TEXT NOT NULL UNIQUE,
                    parent_folder_id INTEGER,
                    name TEXT NOT NULL,
                    ancestors_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    child_count INTEGER,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(parent_folder_id) REFERENCES folders(id)
                );

                CREATE INDEX IF NOT EXISTS idx_folders_status
                    ON folders(status);

                CREATE INDEX IF NOT EXISTS idx_folders_parent
                    ON folders(parent_folder_id);

                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drive_id TEXT NOT NULL,
                    parent_folder_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    child_type TEXT NOT NULL,
                    local_path TEXT NOT NULL UNIQUE,
                    resolved_path TEXT,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(parent_folder_id) REFERENCES folders(id)
                );

                CREATE INDEX IF NOT EXISTS idx_files_parent
                    ON files(parent_folder_id);

                CREATE INDEX IF NOT EXISTS idx_files_status
                    ON files(status);
                """
            )

            meta = {
                row["key"]: row["value"]
                for row in conn.execute("SELECT key, value FROM meta")
            }

            if not meta:
                stamp = now_iso()
                with self.transaction() as tx:
                    tx.executemany(
                        "INSERT INTO meta(key, value) VALUES (?, ?)",
                        [
                            ("schema_version", SCHEMA_VERSION),
                            ("root_id", root_id),
                            ("output", str(output)),
                            ("created_at", stamp),
                        ],
                    )
                    tx.execute(
                        """
                        INSERT INTO folders(
                            drive_id, local_path, parent_folder_id, name,
                            ancestors_json, status, attempts, child_count,
                            last_error, created_at, updated_at
                        )
                        VALUES (?, ?, NULL, ?, '[]', 'pending', 0, NULL,
                                NULL, ?, ?)
                        """,
                        (
                            root_id,
                            str(output),
                            "__ROOT__",
                            stamp,
                            stamp,
                        ),
                    )
                return True

            if meta.get("schema_version") != SCHEMA_VERSION:
                raise RuntimeError(
                    "Nieobsługiwana wersja download_state.sqlite: "
                    f"{meta.get('schema_version')!r}; oczekiwano "
                    f"{SCHEMA_VERSION!r}. Użyj --reset-state, jeśli chcesz "
                    "zacząć indeksowanie od zera."
                )

            if meta.get("root_id") != root_id:
                raise RuntimeError(
                    "Istniejący SQLite dotyczy innego folderu Google Drive.\n"
                    f"DB root: {meta.get('root_id')}\n"
                    f"Nowy root: {root_id}\n"
                    "Użyj innego --state-db albo --reset-state."
                )

            if Path(meta.get("output", "")).resolve() != output.resolve():
                raise RuntimeError(
                    "Istniejący SQLite dotyczy innego katalogu wyjściowego.\n"
                    f"DB output: {meta.get('output')}\n"
                    f"Nowy output: {output}\n"
                    "Użyj innego --state-db albo --reset-state."
                )

        return fresh

    def recover_after_interruption(self) -> None:
        conn = self._conn()
        stamp = now_iso()
        with conn:
            # A listing that did not make it to SQLite must be repeated.
            conn.execute(
                """
                UPDATE folders
                SET status='pending', updated_at=?
                WHERE status='listing'
                """,
                (stamp,),
            )

            # A persisted listing never needs to be fetched again.
            conn.execute(
                """
                UPDATE folders
                SET status='listed', updated_at=?
                WHERE status='processing'
                """,
                (stamp,),
            )

            # gdown keeps the .part file. Next run can use resume=True.
            conn.execute(
                """
                UPDATE files
                SET status='pending', updated_at=?
                WHERE status='downloading'
                """,
                (stamp,),
            )

    def retry_failed(self) -> tuple[int, int]:
        conn = self._conn()
        stamp = now_iso()
        with self.transaction() as tx:
            cur1 = tx.execute(
                """
                UPDATE folders
                SET status='pending', last_error=NULL, updated_at=?
                WHERE status='failed'
                """,
                (stamp,),
            )
            retried_folders = cur1.rowcount

            cur2 = tx.execute(
                """
                UPDATE files
                SET status='pending', last_error=NULL, updated_at=?
                WHERE status='failed'
                """,
                (stamp,),
            )
            retried_files = cur2.rowcount

            # A folder can have been marked done while one of its direct files
            # was terminal-failed. Re-open only those parents.
            tx.execute(
                """
                UPDATE folders
                SET status='listed', updated_at=?
                WHERE status='done'
                  AND EXISTS (
                    SELECT 1
                    FROM files
                    WHERE files.parent_folder_id = folders.id
                      AND files.status='pending'
                  )
                """,
                (stamp,),
            )

        return retried_folders, retried_files

    def reconcile_local_files(self) -> int:
        """
        If a DB row says a file is complete but the local file disappeared,
        make it pending again. This protects against manual deletions between runs.
        """
        conn = self._conn()
        rows = conn.execute(
            """
            SELECT id, local_path, resolved_path
            FROM files
            WHERE status IN ('done', 'skipped')
            """
        ).fetchall()

        missing: list[int] = []
        for row in rows:
            candidate = Path(row["resolved_path"] or row["local_path"])
            if not candidate.is_file():
                missing.append(row["id"])

        if not missing:
            return 0

        stamp = now_iso()
        with self.transaction() as tx:
            tx.executemany(
                """
                UPDATE files
                SET status='pending', resolved_path=NULL, size_bytes=0,
                    last_error='Local completed file was missing on resume',
                    updated_at=?
                WHERE id=?
                """,
                [(stamp, file_id) for file_id in missing],
            )
            tx.execute(
                """
                UPDATE folders
                SET status='listed', updated_at=?
                WHERE status='done'
                  AND EXISTS (
                    SELECT 1
                    FROM files
                    WHERE files.parent_folder_id = folders.id
                      AND files.status='pending'
                  )
                """,
                (stamp,),
            )

        return len(missing)

    def resumable_folder_ids(self) -> list[int]:
        conn = self._conn()
        return [
            row["id"]
            for row in conn.execute(
                """
                SELECT id
                FROM folders
                WHERE status IN ('pending', 'listed')
                ORDER BY id
                """
            )
        ]

    def get_folder(self, folder_pk: int) -> sqlite3.Row | None:
        return self._conn().execute(
            "SELECT * FROM folders WHERE id=?",
            (folder_pk,),
        ).fetchone()

    def claim_folder(self, folder_pk: int) -> str | None:
        """
        Atomically claim a queued folder.
        Returns original status ('pending' or 'listed'), or None if another
        worker/run already made it non-runnable.
        """
        conn = self._conn()
        row = conn.execute(
            "SELECT status FROM folders WHERE id=?",
            (folder_pk,),
        ).fetchone()
        if row is None or row["status"] not in {"pending", "listed"}:
            return None

        original = row["status"]
        new_status = "listing" if original == "pending" else "processing"
        cur = conn.execute(
            """
            UPDATE folders
            SET status=?, updated_at=?
            WHERE id=? AND status=?
            """,
            (new_status, now_iso(), folder_pk, original),
        )
        if cur.rowcount != 1:
            return None
        return original

    def set_folder_listed_after_stop(self, folder_pk: int) -> None:
        self._conn().execute(
            """
            UPDATE folders
            SET status='listed', updated_at=?
            WHERE id=? AND status='processing'
            """,
            (now_iso(), folder_pk),
        )

    def set_folder_pending_after_stop(self, folder_pk: int) -> None:
        self._conn().execute(
            """
            UPDATE folders
            SET status='pending', updated_at=?
            WHERE id=? AND status='listing'
            """,
            (now_iso(), folder_pk),
        )

    def increment_folder_attempt(self, folder_pk: int) -> None:
        self._conn().execute(
            """
            UPDATE folders
            SET attempts=attempts+1, updated_at=?
            WHERE id=?
            """,
            (now_iso(), folder_pk),
        )

    def fail_folder(self, folder_pk: int, error: str) -> None:
        self._conn().execute(
            """
            UPDATE folders
            SET status='failed', last_error=?, updated_at=?
            WHERE id=?
            """,
            (error, now_iso(), folder_pk),
        )

    def persist_listing(
        self,
        *,
        folder_pk: int,
        children: list[tuple[str, str, str]],
    ) -> list[int]:
        """
        Persist one folder listing atomically.

        Crucial resume guarantee:
        - child rows are inserted,
        - the current folder changes from 'listing' -> 'processing',
        in ONE transaction.

        If the process dies before commit, the next run relists this one folder.
        If commit succeeds, this folder is never traversed on Drive again.
        """
        conn = self._conn()
        folder = conn.execute(
            "SELECT * FROM folders WHERE id=?",
            (folder_pk,),
        ).fetchone()
        if folder is None:
            raise RuntimeError(f"Missing folder row id={folder_pk}")

        parent_path = Path(folder["local_path"])
        ancestors = json.loads(folder["ancestors_json"])
        current_ancestry = ancestors + [folder["drive_id"]]
        stamp = now_iso()

        children = dedupe_children(children)
        newly_inserted_folder_ids: list[int] = []

        with self.transaction() as tx:
            for child_drive_id, child_name, child_type in children:
                child_path = parent_path / child_name

                if child_type == _GoogleDriveFile.TYPE_FOLDER:
                    # A direct ancestry cycle (A -> B -> A) gets its own
                    # terminal status. --retry-failed must not re-enable it.
                    cycle = child_drive_id in current_ancestry
                    status = "cycle" if cycle else "pending"
                    error = (
                        "Shortcut/folder cycle detected; child points to an ancestor."
                        if cycle
                        else None
                    )

                    cur = tx.execute(
                        """
                        INSERT OR IGNORE INTO folders(
                            drive_id, local_path, parent_folder_id, name,
                            ancestors_json, status, attempts, child_count,
                            last_error, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?)
                        """,
                        (
                            child_drive_id,
                            str(child_path),
                            folder_pk,
                            child_name,
                            json.dumps(current_ancestry),
                            status,
                            error,
                            stamp,
                            stamp,
                        ),
                    )
                    if cur.rowcount == 1 and not cycle:
                        newly_inserted_folder_ids.append(cur.lastrowid)

                else:
                    tx.execute(
                        """
                        INSERT OR IGNORE INTO files(
                            drive_id, parent_folder_id, name, child_type,
                            local_path, resolved_path, status, attempts,
                            size_bytes, last_error, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, NULL, 'pending', 0, 0,
                                NULL, ?, ?)
                        """,
                        (
                            child_drive_id,
                            folder_pk,
                            child_name,
                            child_type,
                            str(child_path),
                            stamp,
                            stamp,
                        ),
                    )

            tx.execute(
                """
                UPDATE folders
                SET status='processing', child_count=?, last_error=NULL,
                    updated_at=?
                WHERE id=?
                """,
                (len(children), stamp, folder_pk),
            )

        return newly_inserted_folder_ids

    def direct_child_folder_count(self, folder_pk: int) -> int:
        row = self._conn().execute(
            """
            SELECT COUNT(*) AS n
            FROM folders
            WHERE parent_folder_id=?
            """,
            (folder_pk,),
        ).fetchone()
        return int(row["n"])

    def direct_files(self, folder_pk: int) -> list[sqlite3.Row]:
        return self._conn().execute(
            """
            SELECT *
            FROM files
            WHERE parent_folder_id=?
            ORDER BY id
            """,
            (folder_pk,),
        ).fetchall()

    def mark_folder_done(self, folder_pk: int) -> None:
        self._conn().execute(
            """
            UPDATE folders
            SET status='done', updated_at=?
            WHERE id=?
            """,
            (now_iso(), folder_pk),
        )

    def increment_file_attempt_and_mark_downloading(self, file_pk: int) -> None:
        self._conn().execute(
            """
            UPDATE files
            SET status='downloading',
                attempts=attempts+1,
                updated_at=?
            WHERE id=?
            """,
            (now_iso(), file_pk),
        )

    def set_file_pending_after_stop(self, file_pk: int) -> None:
        self._conn().execute(
            """
            UPDATE files
            SET status='pending', updated_at=?
            WHERE id=? AND status='downloading'
            """,
            (now_iso(), file_pk),
        )

    def mark_file_complete(
        self,
        *,
        file_pk: int,
        status: str,
        resolved_path: Path,
        size_bytes: int,
    ) -> None:
        if status not in {"done", "skipped"}:
            raise ValueError(status)
        self._conn().execute(
            """
            UPDATE files
            SET status=?, resolved_path=?, size_bytes=?,
                last_error=NULL, updated_at=?
            WHERE id=?
            """,
            (
                status,
                str(resolved_path),
                size_bytes,
                now_iso(),
                file_pk,
            ),
        )

    def fail_file(self, file_pk: int, error: str) -> None:
        self._conn().execute(
            """
            UPDATE files
            SET status='failed', last_error=?, updated_at=?
            WHERE id=?
            """,
            (error, now_iso(), file_pk),
        )

    def status_counts(self) -> dict:
        conn = self._conn()

        folder_status = {
            row["status"]: row["n"]
            for row in conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM folders
                GROUP BY status
                """
            )
        }
        file_status = {
            row["status"]: row["n"]
            for row in conn.execute(
                """
                SELECT status, COUNT(*) AS n
                FROM files
                GROUP BY status
                """
            )
        }

        file_size = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE
                    WHEN status IN ('done', 'skipped') THEN size_bytes
                    ELSE 0
                END), 0) AS complete_bytes
            FROM files
            """
        ).fetchone()["complete_bytes"]

        return {
            "folders": folder_status,
            "files": file_status,
            "complete_file_bytes": int(file_size),
        }

    def failed_rows(self) -> list[dict]:
        conn = self._conn()
        rows: list[dict] = []

        for row in conn.execute(
            """
            SELECT *
            FROM folders
            WHERE status IN ('failed', 'cycle')
            ORDER BY local_path
            """
        ):
            rows.append(
                {
                    "kind": (
                        "cycle" if row["status"] == "cycle" else "folder"
                    ),
                    "full_path": row["local_path"],
                    "parent_folder": str(Path(row["local_path"]).parent),
                    "drive_id": row["drive_id"],
                    "url": (
                        "https://drive.google.com/drive/folders/"
                        + row["drive_id"]
                    ),
                    "attempts": row["attempts"],
                    "error": row["last_error"] or "",
                }
            )

        for row in conn.execute(
            """
            SELECT files.*, folders.local_path AS parent_path
            FROM files
            JOIN folders ON folders.id = files.parent_folder_id
            WHERE files.status='failed'
            ORDER BY files.local_path
            """
        ):
            rows.append(
                {
                    "kind": "file",
                    "full_path": row["local_path"],
                    "parent_folder": row["parent_path"],
                    "drive_id": row["drive_id"],
                    "url": (
                        "https://drive.google.com/open?id="
                        + row["drive_id"]
                    ),
                    "attempts": row["attempts"],
                    "error": row["last_error"] or "",
                }
            )

        return rows


def dedupe_children(
    children: list[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """
    Google Drive permits duplicate sibling names; a filesystem cannot preserve
    both at one identical path. Keep the first name unchanged and suffix later
    duplicates with __dup2, __dup3, ...
    """
    seen: dict[str, int] = {}
    result: list[tuple[str, str, str]] = []

    for child_id, raw_name, child_type in children:
        name = _sanitize_filename(filename=raw_name)
        n = seen.get(name, 0) + 1
        seen[name] = n

        if n > 1:
            if child_type == _GoogleDriveFile.TYPE_FOLDER:
                name = f"{name}__dup{n}"
            else:
                p = Path(name)
                if p.suffix:
                    name = f"{p.stem}__dup{n}{p.suffix}"
                else:
                    name = f"{name}__dup{n}"

        result.append((child_id, name, child_type))

    return result


def parse_embedded_folder_view(
    *,
    sess,
    folder_id: str,
    timeout: float,
) -> list[tuple[str, str, str]]:
    """
    One-level equivalent of gdown 6.x's embeddedfolderview parser, but with an
    explicit request timeout so a worker cannot hang forever.
    """
    params = urllib.parse.urlencode({"id": folder_id})
    url = f"https://drive.google.com/embeddedfolderview?{params}"

    res = sess.get(url, verify=True, timeout=timeout)
    if res.status_code != HTTPStatus.OK:
        raise DownloadError(
            f"Failed to retrieve folder contents for folder ID: "
            f"{folder_id} (status code {res.status_code})."
        )

    soup = bs4.BeautifulSoup(res.text, features="html.parser")
    if soup.title is None or soup.title.string is None:
        raise DownloadError(
            f"Failed to parse folder contents for folder ID: {folder_id}."
        )

    children: list[tuple[str, str, str]] = []

    for a_tag in soup.find_all(name="a"):
        href = a_tag.get("href", "")
        if not isinstance(href, str):
            continue

        file_match = re.match(
            r"https://drive\.google\.com/file/d/([-\w]{25,})/view",
            href,
        )
        if file_match:
            children.append(
                (
                    file_match.group(1),
                    a_tag.get_text(strip=True),
                    "application/octet-stream",
                )
            )
            continue

        docs_match = re.match(
            r"https://docs\.google\.com/(\w+)/d/([-\w]{25,})/",
            href,
        )
        if docs_match:
            kind, file_id = docs_match.groups()
            file_type = (
                "application/vnd.google-apps."
                + kind.removesuffix("s")
            )
            children.append(
                (
                    file_id,
                    a_tag.get_text(strip=True),
                    file_type,
                )
            )
            continue

        child_folder_id = _parse_google_drive_folder_id(url=href)
        if child_folder_id is not None:
            children.append(
                (
                    child_folder_id,
                    a_tag.get_text(strip=True),
                    _GoogleDriveFile.TYPE_FOLDER,
                )
            )

    return children


class RuntimeState:
    def __init__(
        self,
        *,
        db: Database,
        output: Path,
        workers: int,
        retries: int,
        backoff: float,
        listing_timeout: float,
        run_log_dir: Path,
    ):
        self.db = db
        self.output = output
        self.workers = workers
        self.retries = retries
        self.backoff = backoff
        self.listing_timeout = listing_timeout

        self.stop_event = threading.Event()

        self.run_stats = RunStats()
        self.stats_lock = threading.Lock()

        self.console = Console()
        self.progress_lock = threading.Lock()

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.fields[worker]:<3}[/]"),
            TextColumn("{task.fields[status]:<14}"),
            BarColumn(bar_width=18),
            TextColumn("{task.fields[count]:>9}"),
            TextColumn("{task.fields[file_pct]:>8}"),
            TextColumn("[dim]{task.fields[folder]}[/]"),
            TextColumn("→ {task.fields[item]}"),
            TimeElapsedColumn(),
            console=self.console,
            refresh_per_second=8,
            expand=True,
        )
        self.task_ids: dict[int, int] = {}

        self.log_dir = run_log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_log = self.log_dir / "run.log"
        self.failure_csv = self.log_dir / "failures.csv"
        self.summary_json = self.log_dir / "summary.json"

        logging.basicConfig(
            filename=self.run_log,
            level=logging.INFO,
            format=(
                "%(asctime)s [%(levelname)s] "
                "[%(threadName)s] %(message)s"
            ),
            force=True,
        )

        # gdown uses the filesystem .part files for resumable file bodies.
        self.tmp_root = output.parent / ".paczka_download_tmp"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    def inc(self, field: str, amount: int = 1) -> None:
        with self.stats_lock:
            setattr(
                self.run_stats,
                field,
                getattr(self.run_stats, field) + amount,
            )

    def snapshot_run_stats(self) -> RunStats:
        with self.stats_lock:
            return RunStats(**asdict(self.run_stats))

    def reset_worker(
        self,
        worker_no: int,
        *,
        status: str,
        folder: str = "",
        item: str = "",
    ) -> None:
        task_id = self.task_ids[worker_no]
        with self.progress_lock:
            self.progress.reset(
                task_id,
                total=1,
                completed=0,
                worker=f"W{worker_no}",
                status=status,
                count="…",
                file_pct="",
                folder=shorten(folder, 52),
                item=shorten(item, 45),
            )

    def update_worker(
        self,
        worker_no: int,
        *,
        status: str,
        folder: str,
        item: str = "",
        completed: int | None = None,
        total: int | None = None,
        count: str | None = None,
        file_pct: str = "",
    ) -> None:
        kwargs = {
            "status": status,
            "folder": shorten(folder, 52),
            "item": shorten(item, 45),
            "file_pct": file_pct,
        }
        if completed is not None:
            kwargs["completed"] = completed
        if total is not None:
            kwargs["total"] = max(total, 1)
        if count is not None:
            kwargs["count"] = count

        with self.progress_lock:
            self.progress.update(
                self.task_ids[worker_no],
                **kwargs,
            )


def list_folder_with_retry(
    state: RuntimeState,
    worker_no: int,
    sess,
    folder: sqlite3.Row,
) -> list[tuple[str, str, str]]:
    folder_path = Path(folder["local_path"])
    folder_display = relative_display(folder_path, state.output)

    last_error = ""

    for attempt in range(1, state.retries + 1):
        if state.stop_event.is_set():
            raise GracefulStop()

        state.db.increment_folder_attempt(folder["id"])

        state.reset_worker(
            worker_no,
            status="trawersowanie",
            folder=folder_display,
            item=f"lista folderu {attempt}/{state.retries}",
        )

        try:
            time.sleep(random.uniform(0.05, 0.30))
            children = parse_embedded_folder_view(
                sess=sess,
                folder_id=folder["drive_id"],
                timeout=state.listing_timeout,
            )
            state.inc("folders_listed_this_run")
            logging.info(
                "Listed folder drive_id=%s path=%s children=%d",
                folder["drive_id"],
                folder_path,
                len(children),
            )
            return children

        except GracefulStop:
            raise
        except Exception as exc:
            last_error = repr(exc)
            logging.warning(
                "Listing failed %d/%d drive_id=%s path=%s error=%r",
                attempt,
                state.retries,
                folder["drive_id"],
                folder_path,
                exc,
            )

            if attempt < state.retries:
                state.inc("folder_retries")
                state.update_worker(
                    worker_no,
                    status=f"retry {attempt}/{state.retries}",
                    folder=folder_display,
                    item=str(exc),
                    count="…",
                )
                backoff_wait(
                    state.stop_event,
                    state.backoff,
                    attempt,
                )

    state.db.fail_folder(folder["id"], last_error)
    state.inc("folders_failed_this_run")
    raise DownloadError(last_error)


def is_google_native(child_type: str) -> bool:
    return child_type.startswith(
        "application/vnd.google-apps."
    ) and child_type != _GoogleDriveFile.TYPE_FOLDER


def existing_local_file(
    file_row: sqlite3.Row,
) -> Path | None:
    """
    Detect a completed local file when SQLite does not yet know it, e.g. after
    resetting state while keeping 00_SOURCES.
    """
    base = Path(file_row["local_path"])

    if not is_google_native(file_row["child_type"]):
        if base.is_file() and base.stat().st_size > 0:
            return base
        return None

    known_ext = GOOGLE_NATIVE_EXT.get(file_row["child_type"])
    if known_ext:
        candidate = base.with_name(base.name + known_ext)
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate

    return None


def download_file_with_retry(
    state: RuntimeState,
    worker_no: int,
    file_row: sqlite3.Row,
    *,
    folder_display: str,
    folder_completed: int,
    folder_total: int,
) -> str:
    """
    Return 'done', 'skipped', or 'failed'.
    Raise GracefulStop without poisoning DB failure state.
    """
    preexisting = existing_local_file(file_row)
    if preexisting is not None:
        size = preexisting.stat().st_size
        state.db.mark_file_complete(
            file_pk=file_row["id"],
            status="skipped",
            resolved_path=preexisting,
            size_bytes=size,
        )
        state.inc("files_skipped_existing_this_run")
        state.inc("skipped_bytes_this_run", size)
        return "skipped"

    file_id = file_row["drive_id"]
    file_name = file_row["name"]
    child_type = file_row["child_type"]
    base_target = Path(file_row["local_path"])
    base_target.parent.mkdir(parents=True, exist_ok=True)

    url = f"https://drive.google.com/uc?id={file_id}"
    open_url = f"https://drive.google.com/open?id={file_id}"

    last_error = ""

    for attempt in range(1, state.retries + 1):
        if state.stop_event.is_set():
            raise GracefulStop()

        state.db.increment_file_attempt_and_mark_downloading(
            file_row["id"]
        )

        last_percent = {"value": None}

        def on_progress(
            bytes_so_far: int,
            bytes_total: int | None,
        ) -> None:
            # gdown explicitly allows a progress callback to raise and abort.
            # The .part file remains available for resume=True on the next run.
            if state.stop_event.is_set():
                raise GracefulStop()

            if bytes_total and bytes_total > 0:
                pct = int(bytes_so_far * 100 / bytes_total)
                if pct == last_percent["value"]:
                    return
                last_percent["value"] = pct
                pct_text = f"{pct:3d}%"
            else:
                pct_text = human_bytes(bytes_so_far)

            state.update_worker(
                worker_no,
                status="pobieranie",
                folder=folder_display,
                item=file_name,
                completed=folder_completed,
                total=folder_total,
                count=f"{folder_completed}/{folder_total}",
                file_pct=pct_text,
            )

        try:
            state.update_worker(
                worker_no,
                status="pobieranie",
                folder=folder_display,
                item=f"{file_name} [{attempt}/{state.retries}]",
                completed=folder_completed,
                total=folder_total,
                count=f"{folder_completed}/{folder_total}",
                file_pct="0%",
            )

            if is_google_native(child_type):
                # Let gdown discover the export extension (.docx/.xlsx/.pptx
                # and other Google-native formats) inside a deterministic temp
                # directory. That also makes .part resumption deterministic.
                temp_dir = state.tmp_root / file_id
                temp_dir.mkdir(parents=True, exist_ok=True)

                result = gdown.download(
                    url=url,
                    output=str(temp_dir) + os.sep,
                    quiet=True,
                    use_cookies=False,
                    verify=True,
                    resume=True,
                    progress=on_progress,
                )

                if not isinstance(result, str):
                    raise RuntimeError(
                        f"Unexpected gdown result: {result!r}"
                    )

                downloaded_tmp = Path(result)
                if not downloaded_tmp.is_file():
                    raise RuntimeError(
                        f"gdown output does not exist: "
                        f"{downloaded_tmp}"
                    )

                export_ext = downloaded_tmp.suffix
                final_target = base_target.with_name(
                    base_target.name + export_ext
                )

                if (
                    final_target.is_file()
                    and final_target.stat().st_size > 0
                ):
                    downloaded_tmp.unlink(missing_ok=True)
                    status = "skipped"
                else:
                    os.replace(downloaded_tmp, final_target)
                    status = "done"

                size = final_target.stat().st_size
                state.db.mark_file_complete(
                    file_pk=file_row["id"],
                    status=status,
                    resolved_path=final_target,
                    size_bytes=size,
                )

                try:
                    temp_dir.rmdir()
                except OSError:
                    pass

            else:
                result = gdown.download(
                    url=url,
                    output=str(base_target),
                    quiet=True,
                    use_cookies=False,
                    verify=True,
                    resume=True,
                    progress=on_progress,
                )

                if not isinstance(result, str):
                    raise RuntimeError(
                        f"Unexpected gdown result: {result!r}"
                    )

                final_target = Path(result)
                if not final_target.is_file():
                    raise RuntimeError(
                        f"gdown output does not exist: {final_target}"
                    )

                size = final_target.stat().st_size
                status = "done"
                state.db.mark_file_complete(
                    file_pk=file_row["id"],
                    status=status,
                    resolved_path=final_target,
                    size_bytes=size,
                )

            if status == "done":
                state.inc("files_downloaded_this_run")
                state.inc("downloaded_bytes_this_run", size)
            else:
                state.inc("files_skipped_existing_this_run")
                state.inc("skipped_bytes_this_run", size)

            logging.info(
                "File complete status=%s url=%s path=%s",
                status,
                open_url,
                final_target,
            )
            return status

        except GracefulStop:
            # Preserve gdown's .part file and make this row resumable.
            state.db.set_file_pending_after_stop(file_row["id"])
            logging.info(
                "Graceful stop during file %s path=%s",
                open_url,
                base_target,
            )
            raise

        except Exception as exc:
            last_error = repr(exc)
            logging.warning(
                "Download failed %d/%d url=%s path=%s error=%r",
                attempt,
                state.retries,
                open_url,
                base_target,
                exc,
            )

            if attempt < state.retries:
                state.inc("file_retries")
                state.update_worker(
                    worker_no,
                    status=f"retry {attempt}/{state.retries}",
                    folder=folder_display,
                    item=file_name,
                    completed=folder_completed,
                    total=folder_total,
                    count=f"{folder_completed}/{folder_total}",
                    file_pct="",
                )
                # It is okay to leave DB status='downloading' during backoff:
                # a crash will reset it to pending on the next start.
                backoff_wait(
                    state.stop_event,
                    state.backoff,
                    attempt,
                )

    state.db.fail_file(file_row["id"], last_error)
    state.inc("files_failed_this_run")
    logging.error(
        "Giving up file %s path=%s error=%s",
        open_url,
        base_target,
        last_error,
    )
    return "failed"


def process_folder(
    state: RuntimeState,
    worker_no: int,
    sess,
    folder_pk: int,
    jobs: queue.Queue,
) -> None:
    claimed_from = state.db.claim_folder(folder_pk)
    if claimed_from is None:
        return

    folder = state.db.get_folder(folder_pk)
    if folder is None:
        return

    folder_path = Path(folder["local_path"])
    folder_path.mkdir(parents=True, exist_ok=True)
    folder_display = relative_display(folder_path, state.output)

    try:
        if claimed_from == "pending":
            children = list_folder_with_retry(
                state,
                worker_no,
                sess,
                folder,
            )

            if state.stop_event.is_set():
                state.db.set_folder_pending_after_stop(folder_pk)
                raise GracefulStop()

            new_child_folder_ids = state.db.persist_listing(
                folder_pk=folder_pk,
                children=children,
            )

            # Only brand-new rows are enqueued here. On a later program run all
            # persisted pending/listed folders are reconstructed from SQLite.
            if not state.stop_event.is_set():
                for child_pk in new_child_folder_ids:
                    jobs.put(child_pk)

        else:
            state.inc("folders_resumed_without_listing")
            logging.info(
                "Resume folder without Drive re-listing: %s",
                folder_path,
            )

        if state.stop_event.is_set():
            state.db.set_folder_listed_after_stop(folder_pk)
            raise GracefulStop()

        # Direct subfolders are considered complete for THIS worker as soon as
        # they are persisted/queued. Their own worker will handle their contents.
        subfolder_count = state.db.direct_child_folder_count(folder_pk)
        files = state.db.direct_files(folder_pk)
        total = subfolder_count + len(files)

        terminal_files = sum(
            1
            for row in files
            if row["status"] in TERMINAL_FILE_STATUSES
        )
        completed = subfolder_count + terminal_files

        state.update_worker(
            worker_no,
            status="przetwarzanie",
            folder=folder_display,
            item="",
            completed=completed if total else 1,
            total=total if total else 1,
            count=f"{completed}/{total}",
            file_pct="",
        )

        for file_row in files:
            if state.stop_event.is_set():
                state.db.set_folder_listed_after_stop(folder_pk)
                raise GracefulStop()

            if file_row["status"] in TERMINAL_FILE_STATUSES:
                continue

            download_file_with_retry(
                state,
                worker_no,
                file_row,
                folder_display=folder_display,
                folder_completed=completed,
                folder_total=total,
            )
            completed += 1

            state.update_worker(
                worker_no,
                status="przetwarzanie",
                folder=folder_display,
                item=file_row["name"],
                completed=completed if total else 1,
                total=total if total else 1,
                count=f"{completed}/{total}",
                file_pct="",
            )

        state.db.mark_folder_done(folder_pk)

        state.update_worker(
            worker_no,
            status="folder gotowy",
            folder=folder_display,
            item="",
            completed=total if total else 1,
            total=total if total else 1,
            count=f"{total}/{total}",
            file_pct="",
        )

    except GracefulStop:
        # 'listing' must be traversed again; 'processing' can resume from DB.
        latest = state.db.get_folder(folder_pk)
        if latest is not None:
            if latest["status"] == "listing":
                state.db.set_folder_pending_after_stop(folder_pk)
            elif latest["status"] == "processing":
                state.db.set_folder_listed_after_stop(folder_pk)
        raise

    except Exception as exc:
        # list_folder_with_retry already marks final listing failures as failed.
        latest = state.db.get_folder(folder_pk)
        if latest is not None and latest["status"] == "processing":
            # Unexpected local/file-processing error: preserve the listing and
            # resume it later rather than throwing away the checkpoint.
            state.db.set_folder_listed_after_stop(folder_pk)

        logging.exception(
            "Unexpected folder processing exception path=%s: %r",
            folder_path,
            exc,
        )


def worker_main(
    state: RuntimeState,
    worker_no: int,
    jobs: queue.Queue,
) -> None:
    threading.current_thread().name = f"drive-worker-{worker_no}"

    sess, _ = _get_session(
        proxy=None,
        use_cookies=False,
        user_agent=FOLDER_UA,
        cookies_file=None,
    )

    try:
        while True:
            if state.stop_event.is_set():
                state.reset_worker(
                    worker_no,
                    status="zatrzymany",
                )
                return

            try:
                folder_pk = jobs.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if state.stop_event.is_set():
                    return

                folder = state.db.get_folder(folder_pk)
                folder_display = (
                    relative_display(
                        Path(folder["local_path"]),
                        state.output,
                    )
                    if folder is not None
                    else f"db:{folder_pk}"
                )

                state.reset_worker(
                    worker_no,
                    status="start",
                    folder=folder_display,
                )

                process_folder(
                    state,
                    worker_no,
                    sess,
                    folder_pk,
                    jobs,
                )

            except GracefulStop:
                state.reset_worker(
                    worker_no,
                    status="zatrzymany",
                )
                return

            finally:
                jobs.task_done()

    finally:
        sess.close()
        state.db.close_thread_connection()


def write_failures_csv(
    db: Database,
    path: Path,
) -> int:
    rows = db.failed_rows()
    fields = [
        "kind",
        "full_path",
        "parent_folder",
        "drive_id",
        "url",
        "attempts",
        "error",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def show_summary(
    state: RuntimeState,
    *,
    elapsed: float,
    interrupted: bool,
    state_db: Path,
) -> None:
    run = state.snapshot_run_stats()
    overall = state.db.status_counts()

    fs = overall["folders"]
    fls = overall["files"]

    table = Table(
        title=(
            "Podsumowanie – przerwano, stan zapisany"
            if interrupted
            else "Podsumowanie pobierania"
        )
    )
    table.add_column("Metryka")
    table.add_column("Wartość", justify="right")

    table.add_row(
        "Czas tego uruchomienia",
        f"{elapsed:.1f} s ({elapsed / 60:.1f} min)",
    )

    table.add_row(
        "Foldery – razem w SQLite",
        str(sum(fs.values())),
    )
    table.add_row(
        "Foldery done / pending / listed / failed / cycle",
        (
            f"{fs.get('done', 0)} / "
            f"{fs.get('pending', 0)} / "
            f"{fs.get('listed', 0)} / "
            f"{fs.get('failed', 0)} / "
            f"{fs.get('cycle', 0)}"
        ),
    )
    table.add_row(
        "Foldery traversowane w tym runie",
        str(run.folders_listed_this_run),
    )
    table.add_row(
        "Foldery wznowione bez traversal",
        str(run.folders_resumed_without_listing),
    )
    table.add_row(
        "Retry folderów w tym runie",
        str(run.folder_retries),
    )

    table.add_row(
        "Pliki – razem w SQLite",
        str(sum(fls.values())),
    )
    table.add_row(
        "Pliki done / skipped / pending / failed",
        (
            f"{fls.get('done', 0)} / "
            f"{fls.get('skipped', 0)} / "
            f"{fls.get('pending', 0)} / "
            f"{fls.get('failed', 0)}"
        ),
    )
    table.add_row(
        "Pobrane w tym runie",
        str(run.files_downloaded_this_run),
    )
    table.add_row(
        "Pominięte istniejące w tym runie",
        str(run.files_skipped_existing_this_run),
    )
    table.add_row(
        "Retry plików w tym runie",
        str(run.file_retries),
    )
    table.add_row(
        "Pobrane bajty w tym runie",
        human_bytes(run.downloaded_bytes_this_run),
    )
    table.add_row(
        "Rozmiar ukończonych wg SQLite",
        human_bytes(overall["complete_file_bytes"]),
    )

    table.add_row("Output", str(state.output))
    table.add_row("State SQLite", str(state_db))
    table.add_row("Logi tego runu", str(state.log_dir))

    state.console.print()
    state.console.print(table)

    if interrupted:
        state.console.print(
            "\n[yellow]Stan jest bezpiecznie zapisany.[/] "
            "Uruchom dokładnie tę samą komendę ponownie. "
            "Foldery ze statusem done nie będą ponownie traversowane, "
            "a foldery listed wznowią pracę z danych w SQLite."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Parallel Google Drive public-folder downloader with SQLite "
            "checkpoint/resume. Preserves the nested Drive structure."
        )
    )

    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Google Drive folder URL or folder ID",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Local output directory",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help=(
            "Concurrent folder workers. 4 is the recommended starting "
            "point; use 2-3 if Google starts returning many 429/500 errors."
        ),
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=6,
        help="Attempts per folder listing or file download",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=2.0,
        help="Initial exponential retry delay in seconds",
    )
    parser.add_argument(
        "--listing-timeout",
        type=float,
        default=90.0,
        help="Timeout in seconds for one folder-listing HTTP request",
    )
    parser.add_argument(
        "--state-db",
        default=None,
        help=(
            "SQLite checkpoint path. Default: "
            "<parent-of-output>/download_state.sqlite"
        ),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            "Put previously failed folders/files back into the pending queue."
        ),
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help=(
            "Delete the traversal SQLite checkpoint and rebuild the Drive "
            "index. Existing files in 00_SOURCES are kept and skipped."
        ),
    )

    return parser.parse_args()


def validate_environment(args: argparse.Namespace) -> None:
    if not 1 <= args.workers <= 16:
        raise SystemExit("--workers musi być pomiędzy 1 a 16")
    if args.retries < 1:
        raise SystemExit("--retries musi być >= 1")
    if args.backoff <= 0:
        raise SystemExit("--backoff musi być > 0")
    if args.listing_timeout <= 0:
        raise SystemExit("--listing-timeout musi być > 0")

    try:
        gv = package_version("gdown")
        major = int(gv.split(".", 1)[0])
    except Exception as exc:
        raise SystemExit(
            f"Nie mogę ustalić wersji gdown: {exc}"
        ) from exc

    if major != 6:
        raise SystemExit(
            f"Ten skrypt jest przygotowany dla gdown 6.x; wykryto {gv}.\n"
            "Uruchom:\n"
            "  pip install -U 'gdown>=6.1,<7' rich"
        )


def main() -> int:
    args = parse_args()
    validate_environment(args)

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    root_id = extract_folder_id(args.url)

    state_db = (
        Path(args.state_db).expanduser().resolve()
        if args.state_db
        else output.parent / "download_state.sqlite"
    )

    if args.reset_state:
        remove_sqlite_files(state_db)

    db = Database(state_db)

    try:
        fresh = db.initialize(
            root_id=root_id,
            output=output,
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc

    # Repair state left by SIGINT, terminal close, reboot, etc.
    db.recover_after_interruption()

    missing_local = db.reconcile_local_files()

    retried_folders = 0
    retried_files = 0
    if args.retry_failed:
        retried_folders, retried_files = db.retry_failed()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log_dir = output.parent / "_download_logs" / stamp

    state = RuntimeState(
        db=db,
        output=output,
        workers=args.workers,
        retries=args.retries,
        backoff=args.backoff,
        listing_timeout=args.listing_timeout,
        run_log_dir=run_log_dir,
    )

    resumed_ids = db.resumable_folder_ids()
    jobs: queue.Queue[int] = queue.Queue()

    for folder_pk in resumed_ids:
        jobs.put(folder_pk)

    state.console.print(
        "[bold]Google Drive → nested downloader + SQLite resume[/]\n"
        f"Root:       https://drive.google.com/drive/folders/{root_id}\n"
        f"Output:     {output}\n"
        f"SQLite:     {state_db}\n"
        f"Workers:    {args.workers}\n"
        f"Retries:    {args.retries}\n"
        f"Tryb:       {'NOWY' if fresh else 'WZNOWIENIE'}\n"
        f"Queue start:{len(resumed_ids):>7} folderów\n"
    )

    if missing_local:
        state.console.print(
            f"[yellow]Reconcile:[/] {missing_local} plików oznaczonych "
            "jako ukończone zniknęło lokalnie → wróciły do pending."
        )

    if args.retry_failed:
        state.console.print(
            "[yellow]Retry failed:[/] "
            f"{retried_folders} folderów, {retried_files} plików."
        )

    if not resumed_ids:
        counts = db.status_counts()
        state.console.print(
            "[green]Brak pending/listed folderów.[/] "
            "Nie ma nic do wznowienia."
        )
        # Still export failures and summary.
        run_log_dir.mkdir(parents=True, exist_ok=True)
        failure_csv = run_log_dir / "failures.csv"
        n_failed = write_failures_csv(db, failure_csv)
        if n_failed:
            state.console.print(
                f"Pozostało {n_failed} failed elementów. "
                "Użyj --retry-failed, aby spróbować ponownie."
            )
        db.close_thread_connection()
        return 0 if n_failed == 0 else 2

    threads: list[threading.Thread] = []
    started = time.monotonic()
    interrupted = False

    try:
        with state.progress:
            for worker_no in range(1, args.workers + 1):
                task_id = state.progress.add_task(
                    "",
                    total=1,
                    completed=0,
                    worker=f"W{worker_no}",
                    status="oczekuje",
                    count="…",
                    file_pct="",
                    folder="",
                    item="",
                )
                state.task_ids[worker_no] = task_id

            for worker_no in range(1, args.workers + 1):
                thread = threading.Thread(
                    target=worker_main,
                    args=(state, worker_no, jobs),
                    daemon=True,
                )
                threads.append(thread)
                thread.start()

            # queue.join() cannot be interrupted cleanly while we intentionally
            # leave queued SQLite work for the next run, so poll unfinished_tasks.
            while True:
                with jobs.all_tasks_done:
                    unfinished = jobs.unfinished_tasks
                if unfinished == 0:
                    break
                time.sleep(0.25)

            # Normal finish: tell idle workers to leave.
            state.stop_event.set()

            for thread in threads:
                thread.join()

    except KeyboardInterrupt:
        interrupted = True
        state.stop_event.set()

        state.console.print(
            "\n[yellow]Ctrl+C:[/] kończę aktywne operacje i zapisuję "
            "checkpoint. Kolejka z SQLite zostanie na następne uruchomienie."
        )

        # gdown progress callbacks see stop_event and abort current transfer;
        # folder HTTP listings have an explicit timeout.
        for thread in threads:
            try:
                thread.join()
            except KeyboardInterrupt:
                state.console.print(
                    "\n[red]Drugie Ctrl+C:[/] wymuszone wyjście. "
                    "SQLite przy kolejnym starcie naprawi statusy "
                    "listing/processing/downloading."
                )
                break

    finally:
        # Idempotent safety net. If a worker was between state transitions,
        # restore resumable statuses.
        db.recover_after_interruption()

    elapsed = time.monotonic() - started

    n_failed = write_failures_csv(
        db,
        state.failure_csv,
    )

    overall = db.status_counts()
    run_stats = state.snapshot_run_stats()

    summary = {
        "timestamp": now_iso(),
        "interrupted": interrupted,
        "root_folder_id": root_id,
        "output": str(output),
        "state_db": str(state_db),
        "workers": args.workers,
        "retries": args.retries,
        "elapsed_seconds": elapsed,
        "run_stats": asdict(run_stats),
        "overall": overall,
        "failed_items": n_failed,
        "failure_csv": str(state.failure_csv),
        "run_log": str(state.run_log),
    }

    state.summary_json.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    show_summary(
        state,
        elapsed=elapsed,
        interrupted=interrupted,
        state_db=state_db,
    )

    if n_failed:
        state.console.print(
            f"\n[yellow]Failed elementy: {n_failed}[/]\n"
            f"Lista: {state.failure_csv}\n"
            "Po zakończeniu reszty możesz uruchomić:\n"
            "  python download_drive_parallel_sqlite.py --retry-failed"
        )

    db.close_thread_connection()

    if interrupted:
        return 130
    return 2 if n_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
