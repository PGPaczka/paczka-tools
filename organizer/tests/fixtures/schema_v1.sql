-- schema.sql — schemat operacyjnej bazy Paczka Organizer (20_WORK/organizer.sqlite).
-- Odpowiada ER-diagramowi z docs/ARCHITEKTURA_FINALv1.md, sekcja 4.
-- Skrypt jest idempotentny (IF NOT EXISTS), więc można go wykonać wielokrotnie.
-- Konwencja czasu: wszystkie daty/czasy to tekst ISO-8601 UTC z sufiksem 'Z'.

-- Wersja schematu zastosowana do tej bazy; klucz naturalny: version.
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Paczki źródłowe (katalogi najwyższego poziomu w 00_SOURCES); klucz naturalny: package_name.
CREATE TABLE IF NOT EXISTS source_packages (
    package_name  TEXT PRIMARY KEY,
    drive_url     TEXT,
    local_path    TEXT,
    downloaded_at TEXT,
    notes         TEXT
);

-- Katalogi w paczkach wraz z podpisami poddrzewa i wskazaniem duplikatu;
-- klucz naturalny: folder_path (POSIX, względem korzenia sources, zaczyna się nazwą paczki).
-- duplicate_of wskazuje na folders(folder_path), więc FK wymusza zapisanie CELU przed duplikatem:
--   skrypt dedupu robi dwa przejścia — najpierw upsert wszystkich folderów bez duplicate_of,
--   potem drugie przejście ustawiające duplicate_of. Dedup jest logiczny, nic nie kasujemy.
CREATE TABLE IF NOT EXISTS folders (
    folder_path          TEXT PRIMARY KEY,
    source_package       TEXT NOT NULL REFERENCES source_packages(package_name),
    file_count           INTEGER,
    total_bytes          INTEGER,
    max_mtime            TEXT,
    structural_signature TEXT,
    tree_hash            TEXT,
    content_set_hash     TEXT,
    duplicate_of         TEXT REFERENCES folders(folder_path),
    status               TEXT NOT NULL DEFAULT 'discovered'
                         CHECK (status IN ('discovered', 'hashed', 'error'))
);

-- Pojedyncze pliki źródłowe (materializacje treści) wraz ze stanem potoku;
-- klucz naturalny: (source_package, source_relative_path), klucz techniczny: file_id.
-- source_relative_path: ścieżka POSIX względem KATALOGU PACZKI, bez nazwy paczki (np. 'sem3/AK/w1.pdf').
-- folder_path: source_package || '/' || dirname(source_relative_path); dla pliku w korzeniu
--   paczki folder_path == source_package. Wylicza to orglib.db.folder_path_for().
CREATE TABLE IF NOT EXISTS files (
    file_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_package       TEXT NOT NULL REFERENCES source_packages(package_name),
    source_relative_path TEXT NOT NULL,
    folder_path          TEXT NOT NULL REFERENCES folders(folder_path),
    filename             TEXT,
    extension            TEXT,
    size_bytes           INTEGER NOT NULL,
    modified_date        TEXT,
    sha256               TEXT,
    normalized_text_hash TEXT,
    simhash              TEXT,
    perceptual_hash      TEXT,
    status               TEXT NOT NULL DEFAULT 'discovered'
                         CHECK (status IN ('discovered', 'hashed', 'extracted', 'classified',
                                           'planned', 'applied', 'verified', 'error')),
    error_message        TEXT,
    UNIQUE (source_package, source_relative_path)
);

-- Unikalne treści (deduplikacja po zawartości) z wynikami ekstrakcji; klucz naturalny: sha256.
CREATE TABLE IF NOT EXISTS content (
    sha256              TEXT PRIMARY KEY,
    content_kind        TEXT CHECK (content_kind IN ('pdf', 'docx', 'pptx', 'xlsx', 'image',
                                                     'text', 'code', 'archive', 'media', 'other')),
    extracted_text_path TEXT,
    ocr_done            INTEGER NOT NULL DEFAULT 0,
    cas_path            TEXT
);

-- Decyzja klasyfikacyjna dla treści (semestr + przedmiot + slot docelowy); klucz naturalny: sha256.
CREATE TABLE IF NOT EXISTS classifications (
    sha256                TEXT PRIMARY KEY REFERENCES content(sha256),
    semester              INTEGER NOT NULL,
    subject_key           TEXT NOT NULL,
    year                  TEXT,
    category              TEXT,
    slot                  TEXT,
    target_relative_path  TEXT,
    is_outdated           INTEGER NOT NULL DEFAULT 0,
    classification_method TEXT CHECK (classification_method IN ('deterministic', 'heuristic',
                                                                'ai', 'manual')),
    confidence            REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    model_name            TEXT,
    run_id                TEXT,
    decided_at            TEXT
);

-- Relacje między treściami (near-dupe / starsza wersja / powiązane), nigdy kasowanie;
-- klucz naturalny: (source_sha256, target_sha256, relation_type).
CREATE TABLE IF NOT EXISTS relations (
    source_sha256    TEXT NOT NULL REFERENCES content(sha256),
    target_sha256    TEXT NOT NULL REFERENCES content(sha256),
    relation_type    TEXT NOT NULL CHECK (relation_type IN ('near_duplicate', 'older_version',
                                                            'related')),
    confidence       REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    detection_method TEXT,
    reason           TEXT,
    PRIMARY KEY (source_sha256, target_sha256, relation_type),
    CHECK (source_sha256 <> target_sha256)
);

-- Ręczne decyzje człowieka (eksportowane do reports/manual_decisions.jsonl); klucz naturalny: sha256.
-- Świadomie bez FK do content: decyzje muszą dać się zaimportować do świeżej, pustej bazy.
CREATE TABLE IF NOT EXISTS manual_decisions (
    sha256               TEXT PRIMARY KEY,
    decision_type        TEXT NOT NULL CHECK (decision_type IN ('classify', 'relation', 'outdated',
                                                                'skip', 'quarantine')),
    target_relative_path TEXT,
    relation_override    TEXT,
    decided_by           TEXT NOT NULL,
    decided_at           TEXT NOT NULL,
    note                 TEXT
);

-- Pozycje planu (jedna treść może trafić w wiele miejsc docelowych);
-- klucz naturalny: (sha256, target_relative_path).
CREATE TABLE IF NOT EXISTS plan_items (
    sha256               TEXT NOT NULL REFERENCES content(sha256),
    target_relative_path TEXT NOT NULL,
    action               TEXT NOT NULL CHECK (action IN ('copy', 'quarantine', 'skip')),
    status               TEXT NOT NULL DEFAULT 'planned'
                         CHECK (status IN ('planned', 'validated', 'applied', 'verified', 'failed')),
    plan_run_id          TEXT NOT NULL,
    PRIMARY KEY (sha256, target_relative_path)
);

-- Faktycznie wykonane zapisy do repo produktu (audyt apply); klucz naturalny: target_relative_path.
CREATE TABLE IF NOT EXISTS applied (
    target_relative_path TEXT PRIMARY KEY,
    sha256               TEXT NOT NULL REFERENCES content(sha256),
    action               TEXT NOT NULL,
    plan_hash            TEXT NOT NULL,
    applied_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_sha256          ON files (sha256);
CREATE INDEX IF NOT EXISTS idx_files_status          ON files (status);
CREATE INDEX IF NOT EXISTS idx_files_folder_path     ON files (folder_path);
CREATE INDEX IF NOT EXISTS idx_files_source_package  ON files (source_package);
CREATE INDEX IF NOT EXISTS idx_folders_tree_hash     ON folders (tree_hash);
CREATE INDEX IF NOT EXISTS idx_folders_content_set   ON folders (content_set_hash);
CREATE INDEX IF NOT EXISTS idx_folders_structural    ON folders (structural_signature);
CREATE INDEX IF NOT EXISTS idx_folders_duplicate_of  ON folders (duplicate_of);
CREATE INDEX IF NOT EXISTS idx_classifications_subj  ON classifications (semester, subject_key);
CREATE INDEX IF NOT EXISTS idx_plan_items_status     ON plan_items (status);
CREATE INDEX IF NOT EXISTS idx_plan_items_run        ON plan_items (plan_run_id);
CREATE INDEX IF NOT EXISTS idx_relations_target      ON relations (target_sha256);
