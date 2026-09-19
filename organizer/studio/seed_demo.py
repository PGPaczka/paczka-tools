"""Generates a synthetic organizer.sqlite for Paczka Studio development.

Creates a realistic demo database with ~700 files across ~20 subjects so the
Studio web UI has data to display without running the full pipeline on real
source folders.

Usage:
    python -m studio.seed_demo                        # default path from paths.yaml
    python -m studio.seed_demo --db /tmp/demo.sqlite  # custom path
    python -m studio.seed_demo --force                # overwrite existing
"""

from __future__ import annotations

import hashlib
import random
import sys
from pathlib import Path

_ORGANIZER_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ORGANIZER_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import typer

from orglib import config, db

app = typer.Typer(add_completion=False, help=__doc__)

PACKAGES = ("Drive_2023", "PaczkaGH_2024", "USB_Kowalski")

EXT_KIND: dict[str, str] = {
    ".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".xlsx": "xlsx",
    ".jpg": "image", ".png": "image", ".zip": "archive", ".rar": "archive",
    ".mp4": "media", ".mp3": "media",
    ".py": "code", ".cpp": "code", ".java": "code",
    ".txt": "text", ".md": "text", ".html": "other",
}

EXTENSIONS = [
    *([".pdf"] * 60), *([".docx"] * 10), *([".pptx"] * 8),
    *([".jpg"] * 3), *([".png"] * 2), *([".zip"] * 3),
    *([".mp4"] * 2), *([".mp3"] * 1),
    *([".py"] * 2), *([".cpp"] * 1),
    *([".txt"] * 2), *([".xlsx"] * 2), *([".html"] * 2), *([".java"] * 1), *([".rar"] * 1),
]

CATEGORIES = ("wyklad", "egzamin", "kolokwia", "laboratoria", "cwiczenia",
              "projekt", "opracowania", "inne")

YEARS = ("2020", "2021", "2022", "2023", "2024")

NAME_TEMPLATES = (
    "{skrot}_{year}_wyklad_{n:02d}", "{skrot}_{year}_egzamin",
    "{skrot}_{year}_kol_{n:02d}", "{skrot}_{year}_lab_{n:02d}_instrukcja",
    "{skrot}_notatki", "prezentacja_{n:02d}", "rozwiazanie_{n:02d}",
    "zad{n}", "foto_tablica_{n:02d}", "{skrot}_{year}_projekt",
    "wyklady_all", "materialy_{year}", "lista_zadan_{n:02d}",
)


def _sha(n: int) -> str:
    return hashlib.sha256(str(n).encode()).hexdigest()


def _pick_subjects(
    all_subjects: list[config.Subject], rng: random.Random
) -> dict[str, list[config.Subject]]:
    by_sem: dict[int, list[config.Subject]] = {}
    for s in all_subjects:
        by_sem.setdefault(s.semester, []).append(s)

    target_skrots = {
        "plan_review": {
            (3, "AKO"), (2, "PO"), (4, "SI"), (5, "IO"), (6, "ED"), (7, "ZSBD"),
        },
        "plan_ready": {
            (1, "PP"), (2, "AiSD"), (3, "BD"), (5, "SBD"), (7, "PAI"),
        },
        "ground_truth": {
            (1, "AM"), (2, "MD"), (4, "PT"), (5, "ASK"), (6, "ZBS"), (7, "PGK"),
        },
    }

    picked: dict[str, list[config.Subject]] = {k: [] for k in target_skrots}
    used: set[tuple[int, str]] = set()

    for stage, keys in target_skrots.items():
        for sem, skrot in keys:
            for s in by_sem.get(sem, []):
                if s.skrot == skrot and s.key not in used:
                    picked[stage].append(s)
                    used.add(s.key)
                    break

    return picked


def _gen_filename(skrot: str, ext: str, n: int, rng: random.Random) -> str:
    tmpl = rng.choice(NAME_TEMPLATES)
    year = rng.choice(YEARS)
    try:
        name = tmpl.format(skrot=skrot, year=year, n=n)
    except (KeyError, IndexError):
        name = f"{skrot}_{n:03d}"
    return name + ext


def _seed_packages(conn):
    for pkg in PACKAGES:
        db.upsert(conn, "source_packages", {
            "package_name": pkg, "notes": "demo data",
        }, conflict=("package_name",))


def _seed_folders(conn, picked, rng):
    folders_created: set[str] = set()
    dup_targets: list[str] = []

    for stage, subjects in picked.items():
        for subj in subjects:
            pkg = rng.choice(PACKAGES)
            folder = db.folder_path_for(pkg, f"SEM{subj.semester}/{subj.skrot}/dummy.pdf")
            if folder not in folders_created:
                db.upsert_folder(conn, {
                    "folder_path": folder,
                    "source_package": pkg,
                    "status": "hashed",
                })
                folders_created.add(folder)
                dup_targets.append(folder)

            sem_folder = db.folder_path_for(pkg, f"SEM{subj.semester}/dummy.pdf")
            if sem_folder not in folders_created:
                db.upsert_folder(conn, {
                    "folder_path": sem_folder,
                    "source_package": pkg,
                    "status": "hashed",
                })
                folders_created.add(sem_folder)

    for pkg in PACKAGES:
        if pkg not in folders_created:
            db.upsert_folder(conn, {
                "folder_path": pkg,
                "source_package": pkg,
                "status": "discovered",
            })
            folders_created.add(pkg)

    if len(dup_targets) >= 4:
        dup_src = f"Drive_2023/SEM3/AKO_kopia"
        if dup_src not in folders_created:
            db.upsert_folder(conn, {
                "folder_path": dup_src,
                "source_package": "Drive_2023",
                "status": "hashed",
                "duplicate_of": dup_targets[0],
            })
            folders_created.add(dup_src)
        dup_src2 = f"USB_Kowalski/SEM2/PO_stare"
        if dup_src2 not in folders_created:
            db.upsert_folder(conn, {
                "folder_path": dup_src2,
                "source_package": "USB_Kowalski",
                "status": "hashed",
                "duplicate_of": dup_targets[1] if len(dup_targets) > 1 else dup_targets[0],
            })
            folders_created.add(dup_src2)

    return folders_created


ContentInfo = dict  # sha256 -> {subject, category, ...}


def _seed_content_and_files(
    conn, picked: dict[str, list[config.Subject]], rng: random.Random
) -> ContentInfo:
    content_map: ContentInfo = {}
    sha_counter = 0
    file_rows = []
    content_rows = []

    items_per_stage = {
        "plan_review": (40, 60),
        "plan_ready": (20, 35),
        "ground_truth": (10, 18),
    }

    for stage, subjects in picked.items():
        lo, hi = items_per_stage[stage]
        for subj in subjects:
            n_items = rng.randint(lo, hi)
            pkg = rng.choice(PACKAGES)
            folder = db.folder_path_for(
                pkg, f"SEM{subj.semester}/{subj.skrot}/dummy.pdf"
            )

            for i in range(n_items):
                sha_counter += 1
                sha = _sha(sha_counter)
                ext = rng.choice(EXTENSIONS)
                kind = EXT_KIND[ext]
                fname = _gen_filename(subj.skrot, ext, i + 1, rng)
                rel_path = f"SEM{subj.semester}/{subj.skrot}/{fname}"

                has_text = kind in ("pdf", "docx", "pptx", "text") and rng.random() < 0.7

                content_rows.append({
                    "sha256": sha,
                    "content_kind": kind,
                    "extracted_text_path": f"extracted_text/{sha[:8]}.txt" if has_text else None,
                    "ocr_done": 1 if (has_text and rng.random() < 0.1) else 0,
                })

                if stage == "ground_truth":
                    status = "extracted"
                elif stage == "plan_ready":
                    status = rng.choice(["classified", "planned", "planned"])
                else:
                    status = rng.choice(["extracted", "classified", "classified", "planned"])

                file_rows.append({
                    "source_package": pkg,
                    "source_relative_path": rel_path,
                    "folder_path": folder,
                    "filename": fname,
                    "extension": ext,
                    "size_bytes": rng.randint(1024, 50_000_000),
                    "sha256": sha,
                    "status": status,
                })

                content_map[sha] = {
                    "subject": subj,
                    "stage": stage,
                    "kind": kind,
                    "status": status,
                    "index": i,
                }

                # ~10% duplicate files (same sha, different path)
                if rng.random() < 0.10:
                    other_pkg = rng.choice([p for p in PACKAGES if p != pkg] or [pkg])
                    other_folder = db.folder_path_for(
                        other_pkg, f"SEM{subj.semester}/{subj.skrot}/dummy.pdf"
                    )
                    if other_folder not in {r.get("folder_path") for r in file_rows}:
                        db.upsert_folder(conn, {
                            "folder_path": other_folder,
                            "source_package": other_pkg,
                            "status": "hashed",
                        })
                    file_rows.append({
                        "source_package": other_pkg,
                        "source_relative_path": f"SEM{subj.semester}/{subj.skrot}/kopia_{fname}",
                        "folder_path": other_folder,
                        "filename": f"kopia_{fname}",
                        "extension": ext,
                        "size_bytes": rng.randint(1024, 50_000_000),
                        "sha256": sha,
                        "status": status,
                    })

    # A few error files
    for _ in range(5):
        sha_counter += 1
        sha = _sha(sha_counter)
        pkg = rng.choice(PACKAGES)
        content_rows.append({"sha256": sha, "content_kind": "other"})
        folder_path = db.folder_path_for(pkg, "SEM1/broken/dummy.pdf")
        file_rows.append({
            "source_package": pkg,
            "source_relative_path": f"SEM1/broken/err_{sha_counter}.dat",
            "folder_path": folder_path,
            "filename": f"err_{sha_counter}.dat",
            "extension": ".dat",
            "size_bytes": 0,
            "sha256": sha,
            "status": "error",
            "error_message": "corrupt file header",
        })

    # Ensure every folder referenced by files exists before the FK insert.
    needed_folders: dict[str, str] = {}
    for row in file_rows:
        fp = row["folder_path"]
        if fp not in needed_folders:
            needed_folders[fp] = row["source_package"]
    for fp, pkg in needed_folders.items():
        db.upsert_folder(conn, {
            "folder_path": fp, "source_package": pkg, "status": "hashed",
        })

    db.upsert_many(conn, "content", content_rows, conflict=("sha256",))
    db.upsert_many(conn, "files", file_rows, conflict=("source_package", "source_relative_path"))

    return content_map


def _seed_classifications(
    conn, picked: dict[str, list[config.Subject]],
    content_map: ContentInfo, rng: random.Random,
    thresholds: dict,
):
    auto_min = thresholds.get("confidence", {}).get("auto_apply", 0.90)
    review_min = thresholds.get("confidence", {}).get("review_min", 0.70)

    methods = ("deterministic", "heuristic", "ai")
    rows = []

    for sha, info in content_map.items():
        subj: config.Subject = info["subject"]
        stage = info["stage"]

        if stage == "ground_truth":
            cat = rng.choice(CATEGORIES[:4])
            rows.append({
                "sha256": sha,
                "semester": subj.semester,
                "subject_key": subj.skrot,
                "category": cat,
                "target_relative_path": f"{subj.target_dir}/{cat}/{sha[:8]}{'.pdf'}",
                "is_outdated": 0,
                "classification_method": "manual",
                "confidence": 1.0,
                "run_id": "ground_truth",
                "decided_at": "2026-09-01T00:00:00Z",
                "action": "copy",
                "needs_review": 0,
            })
            continue

        cat = rng.choice(CATEGORIES)
        method = rng.choice(methods)

        if stage == "plan_ready":
            confidence = rng.uniform(auto_min, 1.0)
            needs_review = 0
        else:
            bucket = rng.choices(
                ["auto", "review", "unresolved"], weights=[30, 40, 30]
            )[0]
            if bucket == "auto":
                confidence = rng.uniform(auto_min, 1.0)
            elif bucket == "review":
                confidence = rng.uniform(review_min, auto_min - 0.001)
            else:
                confidence = rng.uniform(0.30, review_min - 0.001)
            needs_review = 1 if bucket in ("review", "unresolved") and rng.random() < 0.5 else 0
            if bucket == "unresolved":
                needs_review = 1

        action = rng.choices(
            ["copy", "skip", "quarantine", "media"], weights=[70, 15, 10, 5]
        )[0]
        if info["kind"] == "media":
            action = "media"

        rows.append({
            "sha256": sha,
            "semester": subj.semester,
            "subject_key": subj.skrot,
            "category": cat,
            "target_relative_path": f"{subj.target_dir}/{cat}/{sha[:8]}{'.pdf'}",
            "is_outdated": 1 if rng.random() < 0.05 else 0,
            "classification_method": method,
            "confidence": round(confidence, 4),
            "run_id": "plan:demo_seed",
            "decided_at": "2026-09-19T12:00:00Z",
            "action": action,
            "reason": f"demo: {method} → {cat}",
            "needs_review": needs_review,
        })

    db.upsert_many(conn, "classifications", rows, conflict=("sha256",))


def _seed_relations(conn, content_map: ContentInfo, rng: random.Random):
    shas = list(content_map.keys())
    if len(shas) < 4:
        return

    rows = []
    by_subject: dict[tuple[int, str], list[str]] = {}
    for sha, info in content_map.items():
        key = info["subject"].key
        by_subject.setdefault(key, []).append(sha)

    for key, group in by_subject.items():
        if len(group) < 3:
            continue
        pairs = min(3, len(group) // 2)
        sample = rng.sample(group, min(pairs * 2, len(group)))
        for i in range(0, len(sample) - 1, 2):
            a, b = sample[i], sample[i + 1]
            if a == b:
                continue
            rel = rng.choice(["near_duplicate", "near_duplicate", "older_version"])
            rows.append({
                "source_sha256": a,
                "target_sha256": b,
                "relation_type": rel,
                "confidence": round(rng.uniform(0.80, 0.99), 3),
                "detection_method": "simhash" if rel == "near_duplicate" else "mtime",
            })

    if rows:
        db.upsert_many(conn, "relations", rows,
                        conflict=("source_sha256", "target_sha256", "relation_type"))


def _seed_plan_items(conn, content_map: ContentInfo, rng: random.Random):
    rows = []
    for sha, info in content_map.items():
        if info["stage"] == "ground_truth":
            continue
        if info["status"] not in ("planned", "applied", "verified"):
            if rng.random() > 0.3:
                continue

        subj = info["subject"]
        cat = rng.choice(CATEGORIES[:4])
        target = f"{subj.target_dir}/{cat}/{sha[:8]}.pdf"
        action = rng.choices(["copy", "skip", "media"], weights=[80, 15, 5])[0]
        if info["kind"] == "media":
            action = "media"

        status = "planned"
        if info["stage"] == "plan_ready" and rng.random() < 0.2:
            status = "validated"

        rows.append({
            "sha256": sha,
            "target_relative_path": target,
            "action": action,
            "status": status,
            "plan_run_id": "plan:demo_seed",
        })

    if rows:
        db.upsert_many(conn, "plan_items", rows,
                        conflict=("sha256", "target_relative_path"))


def _seed_applied(conn, content_map: ContentInfo, rng: random.Random):
    rows = []
    count = 0
    for sha, info in content_map.items():
        if count >= 12:
            break
        if info["stage"] == "plan_ready" and rng.random() < 0.15:
            subj = info["subject"]
            target = f"{subj.target_dir}/wyklad/{sha[:8]}.pdf"
            rows.append({
                "target_relative_path": target,
                "sha256": sha,
                "action": "copy",
                "plan_hash": hashlib.md5(target.encode()).hexdigest(),
                "applied_at": "2026-09-19T14:00:00Z",
            })
            count += 1

    if rows:
        db.upsert_many(conn, "applied", rows, conflict=("target_relative_path",))


def _seed_manual_decisions(conn, content_map: ContentInfo, rng: random.Random):
    rows = []
    candidates = [sha for sha, info in content_map.items()
                   if info["stage"] == "plan_review"]
    sample = rng.sample(candidates, min(5, len(candidates)))
    for sha in sample:
        rows.append({
            "sha256": sha,
            "decision_type": rng.choice(["classify", "classify", "skip"]),
            "target_relative_path": f"paczka/SEM3/AKO_demo/{sha[:8]}.pdf",
            "decided_by": "user",
            "decided_at": "2026-09-19T15:00:00Z",
            "note": "demo manual decision",
        })
    if rows:
        db.upsert_many(conn, "manual_decisions", rows, conflict=("sha256",))


def _print_summary(conn):
    import status_report

    counts = {}
    for table in db.TABLES:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        counts[table] = row["n"]

    print("\n=== Demo database summary ===")
    for table, n in counts.items():
        print(f"  {table:20s} {n:>6d}")

    data = status_report.collect(conn)
    print(f"\n  Files by status:")
    for status, n in sorted(data["files_by_status"].items()):
        print(f"    {status:15s} {n:>5d}")

    subjects = config.iter_subjects()
    stages = {"plan do przeglądu": 0, "plan gotowy": 0,
              "tylko ground truth": 0, "nietknięty": 0}
    for subj in subjects:
        entry = data["per_subject"].get(subj.key)
        if entry:
            stage = status_report.stage_of(dict(entry))
        else:
            stage = "nietknięty"
        stages[stage] += 1

    print(f"\n  Subjects by stage:")
    for stage, n in stages.items():
        print(f"    {stage:25s} {n:>3d}")
    print()


@app.command()
def main(
    db_path: str = typer.Option(
        "", "--db", help="Output path (default: paths.yaml work_db)",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing database"),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility"),
):
    """Generate a synthetic demo database for Paczka Studio."""
    if db_path:
        target = Path(db_path)
    else:
        paths = config.load_paths()
        target = paths.work_db

    if target.exists() and not force:
        print(f"Database already exists: {target}")
        print("Use --force to overwrite or --db to specify another path.")
        raise typer.Exit(1)

    if target.exists() and force:
        target.unlink()
        print(f"Removed existing: {target}")

    rng = random.Random(seed)
    subjects = config.iter_subjects()
    thresholds = config.load_thresholds()
    picked = _pick_subjects(subjects, rng)

    print(f"Creating demo database: {target}")
    print(f"  Subjects with data: {sum(len(v) for v in picked.values())}")

    conn = db.connect(target, init=True)
    try:
        _seed_packages(conn)
        _seed_folders(conn, picked, rng)
        content_map = _seed_content_and_files(conn, picked, rng)
        _seed_classifications(conn, picked, content_map, rng, thresholds)
        _seed_relations(conn, content_map, rng)
        _seed_plan_items(conn, content_map, rng)
        _seed_applied(conn, content_map, rng)
        _seed_manual_decisions(conn, content_map, rng)
        conn.commit()
        _print_summary(conn)
    finally:
        conn.close()

    print(f"Done. Start studio with:")
    print(f"  just studio-dev  # if db is at default path")
    print(f"  python -m studio.api --db {target}  # custom path")


if __name__ == "__main__":
    app()
