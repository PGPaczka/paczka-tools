#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import queue
import random
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Iterable

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

# gdown 6.x internals: we deliberately use the one-level folder parser so that
# a failure in one nested folder does not abort traversal of the whole tree.
from gdown.download import _get_session, _sanitize_filename
from gdown.download_folder import (
    _GoogleDriveFile,
    _parse_embedded_folder_view,
)

DEFAULT_URL = "https://drive.google.com/drive/folders/18mN48s232REZ1NAcQC9Lkm4uEBQ5yKK3"
DEFAULT_OUTPUT = "/home/billy/dev/paczka/PaczkaMerge/00_SOURCES"

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

SENTINEL = object()


@dataclass(frozen=True)
class FolderJob:
    folder_id: str
    local_path: Path
    ancestors: tuple[str, ...]


@dataclass
class Stats:
    folders_queued: int = 0
    folders_listed: int = 0
    folders_failed: int = 0
    cycles_skipped: int = 0

    files_discovered: int = 0
    files_downloaded: int = 0
    files_skipped: int = 0
    files_failed: int = 0

    folder_retries: int = 0
    file_retries: int = 0

    downloaded_file_bytes: int = 0
    skipped_file_bytes: int = 0


class State:
    def __init__(self, output: Path, retries: int, backoff: float, workers: int):
        self.output = output
        self.retries = retries
        self.backoff = backoff
        self.workers = workers

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = output.parent / "_download_logs" / stamp
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.run_log = self.log_dir / "run.log"
        self.failure_jsonl = self.log_dir / "failures.jsonl"
        self.failure_csv = self.log_dir / "failures.csv"
        self.summary_json = self.log_dir / "summary.json"

        self.tmp_root = output.parent / ".paczka_download_tmp"
        self.tmp_root.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            filename=self.run_log,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
            force=True,
        )

        self.stats = Stats()
        self.stats_lock = threading.Lock()

        self.failures: list[dict] = []
        self.failure_lock = threading.Lock()

        self.progress_lock = threading.Lock()
        self.console = Console()

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.fields[worker]:<3}[/]"),
            TextColumn("{task.fields[status]:<14}"),
            BarColumn(bar_width=20),
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

    def inc(self, field: str, amount: int = 1) -> None:
        with self.stats_lock:
            setattr(self.stats, field, getattr(self.stats, field) + amount)

    def get_stats(self) -> Stats:
        with self.stats_lock:
            return Stats(**asdict(self.stats))

    def add_failure(
        self,
        *,
        kind: str,
        full_path: Path,
        item_id: str,
        url: str,
        error: str,
        attempts: int,
        parent_folder: Path | None = None,
    ) -> None:
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "full_path": str(full_path),
            "parent_folder": str(parent_folder) if parent_folder else "",
            "id": item_id,
            "url": url,
            "attempts": attempts,
            "error": error,
        }
        with self.failure_lock:
            self.failures.append(row)
            with self.failure_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def set_worker(
        self,
        worker_no: int,
        *,
        status: str,
        folder: str = "",
        item: str = "",
        completed: int | None = None,
        total: int | None = None,
        count: str | None = None,
        file_pct: str = "",
    ) -> None:
        task_id = self.task_ids[worker_no]
        kwargs = {
            "status": status,
            "folder": shorten(folder, 52),
            "item": shorten(item, 45),
            "file_pct": file_pct,
        }
        if completed is not None:
            kwargs["completed"] = completed
        if total is not None:
            kwargs["total"] = total
        if count is not None:
            kwargs["count"] = count
        with self.progress_lock:
            self.progress.update(task_id, **kwargs)

    def reset_worker(self, worker_no: int, *, status: str, folder: str = "", item: str = "") -> None:
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
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def extract_folder_id(url_or_id: str) -> str:
    if "/folders/" in url_or_id:
        return url_or_id.split("/folders/", 1)[1].split("?", 1)[0].split("/", 1)[0]
    return url_or_id.strip()


def backoff_sleep(base: float, attempt: int) -> float:
    # 2, 4, 8... capped at 60 sec, plus small jitter to avoid workers retrying together.
    wait = min(base * (2 ** max(0, attempt - 1)), 60.0)
    wait += random.uniform(0.0, min(2.0, wait * 0.20))
    time.sleep(wait)
    return wait


def relative_display(path: Path, output: Path) -> str:
    try:
        rel = path.relative_to(output)
        return "." if str(rel) == "." else str(rel)
    except ValueError:
        return str(path)


def dedupe_children(
    children: Iterable[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """
    Google Drive allows duplicate sibling names; local FS does not.
    Keep the first unchanged and suffix later duplicates with __dupN.
    """
    seen: dict[str, int] = {}
    result: list[tuple[str, str, str]] = []

    for child_id, raw_name, child_type in children:
        name = _sanitize_filename(filename=raw_name)
        key = name
        n = seen.get(key, 0) + 1
        seen[key] = n

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


def list_folder_with_retry(
    state: State,
    worker_no: int,
    sess,
    job: FolderJob,
) -> list[tuple[str, str, str]] | None:
    folder_display = relative_display(job.local_path, state.output)
    folder_url = f"https://drive.google.com/drive/folders/{job.folder_id}"

    last_error = ""
    for attempt in range(1, state.retries + 1):
        state.reset_worker(
            worker_no,
            status="trawersowanie",
            folder=folder_display,
            item=f"lista folderu (próba {attempt}/{state.retries})",
        )
        try:
            # Small jitter prevents all workers from hitting embeddedfolderview at once.
            time.sleep(random.uniform(0.05, 0.35))
            _, children = _parse_embedded_folder_view(
                sess=sess,
                folder_id=job.folder_id,
                verify=True,
            )
            state.inc("folders_listed")
            logging.info("Listed folder %s (%d children)", folder_url, len(children))
            return dedupe_children(children)
        except Exception as exc:
            last_error = repr(exc)
            logging.warning(
                "Folder listing failed attempt %d/%d: %s path=%s error=%r",
                attempt,
                state.retries,
                folder_url,
                job.local_path,
                exc,
            )
            if attempt < state.retries:
                state.inc("folder_retries")
                state.set_worker(
                    worker_no,
                    status=f"retry {attempt}/{state.retries}",
                    folder=folder_display,
                    item=str(exc),
                    count="…",
                )
                backoff_sleep(state.backoff, attempt)

    state.inc("folders_failed")
    state.add_failure(
        kind="folder",
        full_path=job.local_path,
        item_id=job.folder_id,
        url=folder_url,
        error=last_error,
        attempts=state.retries,
        parent_folder=job.local_path.parent,
    )
    logging.error("Giving up folder %s path=%s", folder_url, job.local_path)
    return None


def is_google_native(child_type: str) -> bool:
    return child_type.startswith("application/vnd.google-apps.") and (
        child_type != _GoogleDriveFile.TYPE_FOLDER
    )


def expected_native_path(base_path: Path, child_type: str) -> Path | None:
    ext = GOOGLE_NATIVE_EXT.get(child_type)
    if ext:
        return base_path.with_name(base_path.name + ext)
    return None


def download_file_with_retry(
    state: State,
    worker_no: int,
    *,
    file_id: str,
    file_name: str,
    child_type: str,
    parent_dir: Path,
    folder_display: str,
) -> None:
    url = f"https://drive.google.com/uc?id={file_id}"
    open_url = f"https://drive.google.com/open?id={file_id}"
    native = is_google_native(child_type)

    parent_dir.mkdir(parents=True, exist_ok=True)
    base_target = parent_dir / file_name

    # Skip a known completed local target.
    if native:
        known_target = expected_native_path(base_target, child_type)
        if known_target and known_target.exists() and known_target.is_file() and known_target.stat().st_size > 0:
            state.inc("files_skipped")
            state.inc("skipped_file_bytes", known_target.stat().st_size)
            logging.info("Skip existing %s", known_target)
            return
    else:
        if base_target.exists() and base_target.is_file() and base_target.stat().st_size > 0:
            state.inc("files_skipped")
            state.inc("skipped_file_bytes", base_target.stat().st_size)
            logging.info("Skip existing %s", base_target)
            return

    last_error = ""
    for attempt in range(1, state.retries + 1):
        last_percent = {"value": -1}

        def on_progress(bytes_so_far: int, bytes_total: int | None) -> None:
            if bytes_total and bytes_total > 0:
                pct = int(bytes_so_far * 100 / bytes_total)
                # Avoid excessive terminal updates.
                if pct == last_percent["value"]:
                    return
                last_percent["value"] = pct
                pct_text = f"{pct:3d}%"
            else:
                pct_text = human_bytes(bytes_so_far)

            state.set_worker(
                worker_no,
                status="pobieranie",
                folder=folder_display,
                item=file_name,
                file_pct=pct_text,
            )

        try:
            state.set_worker(
                worker_no,
                status="pobieranie",
                folder=folder_display,
                item=f"{file_name} (próba {attempt}/{state.retries})",
                file_pct="0%",
            )

            if native:
                # Google-native files need gdown to resolve the export extension.
                # Use a deterministic temp directory so interrupted transfers can resume.
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
                    raise RuntimeError(f"Unexpected gdown result: {result!r}")

                downloaded_tmp = Path(result)
                if not downloaded_tmp.exists():
                    raise RuntimeError(f"gdown reported missing output: {downloaded_tmp}")

                export_ext = downloaded_tmp.suffix
                final_target = base_target.with_name(base_target.name + export_ext)
                final_target.parent.mkdir(parents=True, exist_ok=True)

                # If a prior run already completed it while this one was resolving,
                # keep the existing completed file.
                if final_target.exists() and final_target.stat().st_size > 0:
                    downloaded_tmp.unlink(missing_ok=True)
                    state.inc("files_skipped")
                    state.inc("skipped_file_bytes", final_target.stat().st_size)
                else:
                    os.replace(downloaded_tmp, final_target)
                    state.inc("files_downloaded")
                    state.inc("downloaded_file_bytes", final_target.stat().st_size)

                try:
                    temp_dir.rmdir()
                except OSError:
                    pass

                logging.info("Downloaded native %s -> %s", open_url, final_target)
                return

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
                raise RuntimeError(f"Unexpected gdown result: {result!r}")

            final_target = Path(result)
            if not final_target.exists():
                raise RuntimeError(f"gdown reported missing output: {final_target}")

            state.inc("files_downloaded")
            state.inc("downloaded_file_bytes", final_target.stat().st_size)
            logging.info("Downloaded %s -> %s", open_url, final_target)
            return

        except Exception as exc:
            last_error = repr(exc)
            logging.warning(
                "File download failed attempt %d/%d: %s path=%s error=%r",
                attempt,
                state.retries,
                open_url,
                base_target,
                exc,
            )
            if attempt < state.retries:
                state.inc("file_retries")
                state.set_worker(
                    worker_no,
                    status=f"retry {attempt}/{state.retries}",
                    folder=folder_display,
                    item=file_name,
                    file_pct="",
                )
                backoff_sleep(state.backoff, attempt)

    state.inc("files_failed")
    state.add_failure(
        kind="file",
        full_path=base_target,
        item_id=file_id,
        url=open_url,
        error=last_error,
        attempts=state.retries,
        parent_folder=parent_dir,
    )
    logging.error("Giving up file %s path=%s", open_url, base_target)


def process_folder(
    state: State,
    worker_no: int,
    sess,
    job: FolderJob,
    jobs: queue.Queue,
) -> None:
    job.local_path.mkdir(parents=True, exist_ok=True)
    folder_display = relative_display(job.local_path, state.output)

    children = list_folder_with_retry(state, worker_no, sess, job)
    if children is None:
        return

    total = len(children)
    state.set_worker(
        worker_no,
        status="przetwarzanie",
        folder=folder_display,
        item="",
        completed=0,
        total=max(total, 1),
        count=f"0/{total}",
        file_pct="",
    )

    if total == 0:
        state.set_worker(
            worker_no,
            status="pusty",
            folder=folder_display,
            completed=1,
            total=1,
            count="0/0",
        )
        return

    current_ancestors = job.ancestors + (job.folder_id,)

    for index, (child_id, child_name, child_type) in enumerate(children, start=1):
        if child_type == _GoogleDriveFile.TYPE_FOLDER:
            child_path = job.local_path / child_name
            state.set_worker(
                worker_no,
                status="kolejkowanie",
                folder=folder_display,
                item=child_name + "/",
                count=f"{index - 1}/{total}",
                file_pct="",
            )

            if child_id in current_ancestors:
                state.inc("cycles_skipped")
                state.add_failure(
                    kind="cycle",
                    full_path=child_path,
                    item_id=child_id,
                    url=f"https://drive.google.com/drive/folders/{child_id}",
                    error="Shortcut/folder cycle detected; child points to an ancestor.",
                    attempts=0,
                    parent_folder=job.local_path,
                )
                logging.warning("Cycle skipped: %s -> %s", child_path, child_id)
            else:
                child_path.mkdir(parents=True, exist_ok=True)
                state.inc("folders_queued")
                jobs.put(
                    FolderJob(
                        folder_id=child_id,
                        local_path=child_path,
                        ancestors=current_ancestors,
                    )
                )

        else:
            state.inc("files_discovered")
            download_file_with_retry(
                state,
                worker_no,
                file_id=child_id,
                file_name=child_name,
                child_type=child_type,
                parent_dir=job.local_path,
                folder_display=folder_display,
            )

        state.set_worker(
            worker_no,
            status="przetwarzanie",
            folder=folder_display,
            item=child_name,
            completed=index,
            total=total,
            count=f"{index}/{total}",
            file_pct="",
        )


def worker_main(
    state: State,
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
            job = jobs.get()
            try:
                if job is SENTINEL:
                    state.reset_worker(worker_no, status="gotowe")
                    return

                assert isinstance(job, FolderJob)
                state.reset_worker(
                    worker_no,
                    status="start",
                    folder=relative_display(job.local_path, state.output),
                )

                try:
                    process_folder(state, worker_no, sess, job, jobs)
                except Exception as exc:
                    # Last-resort guard: one unexpected folder bug must not kill a worker.
                    state.inc("folders_failed")
                    state.add_failure(
                        kind="worker-folder",
                        full_path=job.local_path,
                        item_id=job.folder_id,
                        url=f"https://drive.google.com/drive/folders/{job.folder_id}",
                        error=repr(exc),
                        attempts=1,
                        parent_folder=job.local_path.parent,
                    )
                    logging.exception("Unexpected worker error for %s", job.local_path)
            finally:
                jobs.task_done()
    finally:
        sess.close()


def write_failure_csv(state: State) -> None:
    fields = [
        "timestamp",
        "kind",
        "full_path",
        "parent_folder",
        "id",
        "url",
        "attempts",
        "error",
    ]
    with state.failure_lock:
        rows = list(state.failures)

    with state.failure_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def cleanup_tmp_root(state: State) -> None:
    # Keep partial files for failed downloads so a later run can resume them.
    # Remove only truly empty temp directories.
    for path in sorted(state.tmp_root.glob("*")):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    try:
        state.tmp_root.rmdir()
    except OSError:
        pass


def show_summary(state: State, elapsed: float) -> None:
    s = state.get_stats()

    table = Table(title="Podsumowanie pobierania", show_header=True)
    table.add_column("Metryka")
    table.add_column("Wartość", justify="right")

    table.add_row("Czas", f"{elapsed:.1f} s ({elapsed / 60:.1f} min)")
    table.add_row("Foldery zakolejkowane", str(s.folders_queued))
    table.add_row("Foldery odczytane", str(s.folders_listed))
    table.add_row("Foldery zfailowane", str(s.folders_failed))
    table.add_row("Cykle skrótów pominięte", str(s.cycles_skipped))
    table.add_row("Pliki odkryte", str(s.files_discovered))
    table.add_row("Pliki pobrane", str(s.files_downloaded))
    table.add_row("Pliki pominięte (już były)", str(s.files_skipped))
    table.add_row("Pliki zfailowane", str(s.files_failed))
    table.add_row("Retry folderów", str(s.folder_retries))
    table.add_row("Retry plików", str(s.file_retries))
    table.add_row("Rozmiar pobranych plików", human_bytes(s.downloaded_file_bytes))
    table.add_row("Rozmiar pominiętych plików", human_bytes(s.skipped_file_bytes))
    table.add_row("Output", str(state.output))
    table.add_row("Logi", str(state.log_dir))

    state.console.print()
    state.console.print(table)

    if state.failures:
        state.console.print(
            f"[yellow]Nie wszystko się udało.[/] Lista błędów:\n"
            f"  JSONL: {state.failure_jsonl}\n"
            f"  CSV:   {state.failure_csv}"
        )
    else:
        state.console.print("[green]Brak zarejestrowanych błędów.[/]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Parallel public Google Drive tree downloader based on gdown 6.x. "
            "Preserves nested folder structure and isolates failures per folder/file."
        )
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="Google Drive folder URL or folder ID")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Local output directory")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Concurrent worker threads. Start with 4; lower to 2-3 if Google throttles.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=6,
        help="Max attempts per folder listing or file download",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=2.0,
        help="Initial exponential retry delay in seconds",
    )
    return parser.parse_args()


def validate_environment(args: argparse.Namespace) -> None:
    if args.workers < 1 or args.workers > 16:
        raise SystemExit("--workers must be between 1 and 16")
    if args.retries < 1:
        raise SystemExit("--retries must be >= 1")
    if args.backoff <= 0:
        raise SystemExit("--backoff must be > 0")

    try:
        gv = package_version("gdown")
        major = int(gv.split(".", 1)[0])
    except Exception as exc:
        raise SystemExit(f"Cannot determine gdown version: {exc}") from exc

    if major != 6:
        raise SystemExit(
            f"This script is written for gdown 6.x private folder-parser API; found gdown {gv}. "
            "Install with: pip install -U 'gdown>=6.1,<7'"
        )


def main() -> int:
    args = parse_args()
    validate_environment(args)

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    root_id = extract_folder_id(args.url)
    state = State(
        output=output,
        retries=args.retries,
        backoff=args.backoff,
        workers=args.workers,
    )

    state.console.print(
        f"[bold]Google Drive tree downloader[/]\n"
        f"Root:    https://drive.google.com/drive/folders/{root_id}\n"
        f"Output:  {output}\n"
        f"Workers: {args.workers}\n"
        f"Retries: {args.retries}\n"
    )

    jobs: queue.Queue = queue.Queue()
    state.inc("folders_queued")
    jobs.put(FolderJob(folder_id=root_id, local_path=output, ancestors=()))

    started = time.monotonic()
    threads: list[threading.Thread] = []

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

        # Wait until root + every dynamically discovered folder has completed.
        jobs.join()

        # Stop workers cleanly.
        for _ in threads:
            jobs.put(SENTINEL)
        for thread in threads:
            thread.join()

    elapsed = time.monotonic() - started

    write_failure_csv(state)
    cleanup_tmp_root(state)

    summary = {
        "started_output": str(output),
        "root_folder_id": root_id,
        "workers": args.workers,
        "retries": args.retries,
        "elapsed_seconds": elapsed,
        "stats": asdict(state.get_stats()),
        "failures": len(state.failures),
        "failure_jsonl": str(state.failure_jsonl),
        "failure_csv": str(state.failure_csv),
        "run_log": str(state.run_log),
    }
    state.summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    show_summary(state, elapsed)

    # Nonzero exit if anything failed, useful for scripting.
    return 2 if state.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
