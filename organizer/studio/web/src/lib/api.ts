/**
 * Klient API studia. Typy odpowiadają kształtowi z `studio/api/queries.py`;
 * widok niczego nie dolicza — jeśli jakiejś liczby tu nie ma, ma ją dodać backend
 * (studio/AGENTS.md, reguła 1).
 */

export interface Thresholds {
  auto_apply: number;
  review_min: number;
}

export interface Totals {
  packages: number;
  folders: number;
  duplicate_folders: number;
  files: number;
  files_by_status: Record<string, number>;
  contents: number;
  with_text: number;
  relations: number;
  plan_items: number;
  applied: number;
  subjects: number;
}

export interface SubjectRow {
  semester: number;
  skrot: string;
  nazwa: string;
  grupa: string;
  target_dir: string;
  forms: string[];
  aliases: string[];
  stage: string;
  ground_truth: number;
  planned: number;
  needs_review: number;
  actions: Record<string, number>;
  decided_at: string | null;
  run_id: string | null;
}

export interface QueueStage {
  stage: string;
  count: number;
  subjects: Array<Pick<SubjectRow, 'semester' | 'skrot' | 'nazwa' | 'grupa' | 'needs_review' | 'planned' | 'ground_truth'>>;
}

export interface Dashboard {
  thresholds: Thresholds;
  totals: Totals;
  subjects: SubjectRow[];
  queue: QueueStage[];
}

export interface CategoryRow {
  category: string;
  count: number;
  needs_review: number;
  min_confidence: number | null;
}

export interface SubjectDetail {
  subject: Pick<SubjectRow, 'semester' | 'skrot' | 'nazwa' | 'grupa' | 'target_dir' | 'forms' | 'aliases'>;
  stage: string;
  ground_truth: number;
  planned: number;
  needs_review: number;
  actions: Record<string, number>;
  decided_at: string | null;
  run_id: string | null;
  outdated: number;
  categories: CategoryRow[];
  methods: Record<string, number>;
  confidence: { thresholds: Thresholds; buckets: Record<string, number> };
  ground_truth_categories: Record<string, number>;
}

export interface Item {
  sha256: string;
  content_kind: string | null;
  has_text: number;
  ocr_done: number;
  semester: number | null;
  subject_key: string | null;
  category: string | null;
  slot: string | null;
  target_relative_path: string | null;
  action: string | null;
  reason: string | null;
  confidence: number | null;
  confidence_bucket: string;
  classification_method: string | null;
  needs_review: number | null;
  is_outdated: number | null;
  run_id: string | null;
  decided_at: string | null;
  file_id: number | null;
  source_package: string | null;
  source_relative_path: string | null;
  /** Katalog źródłowy tej kopii — podstawa decyzji hurtowej (S1.6). */
  folder_path: string | null;
  filename: string | null;
  extension: string | null;
  size_bytes: number | null;
  modified_date: string | null;
  file_status: string | null;
  copies: number;
}

export interface ItemsPage {
  total: number;
  limit: number;
  offset: number;
  thresholds: Thresholds;
  items: Item[];
}

export interface ItemFilters {
  semester?: number;
  skrot?: string;
  category?: string;
  action?: string;
  status?: string;
  kind?: string;
  needs_review?: boolean;
  classified?: boolean;
  confidence_min?: number;
  confidence_max?: number;
  include_ground_truth?: boolean;
  limit?: number;
  offset?: number;
}

/**
 * Buduje adres listy pozycji. Puste i nieustawione filtry NIE trafiają do URL-a:
 * pusty parametr znaczyłby dla backendu „kategoria równa pustemu napisowi”,
 * czyli cicho zerową listę zamiast braku filtru.
 */
export function itemsUrl(filters: ItemFilters = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, typeof value === 'boolean' ? String(value) : String(value));
  }
  const query = params.toString();
  return query ? `/api/items?${query}` : '/api/items';
}

/** Adres jednego przedmiotu; `grupa` rozstrzyga kolizje skrótu w semestrze. */
export function subjectUrl(semester: number, skrot: string, grupa?: string): string {
  const base = `/api/subjects/${semester}/${encodeURIComponent(skrot)}`;
  return grupa ? `${base}?grupa=${encodeURIComponent(grupa)}` : base;
}

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, headers: { accept: 'application/json' } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* odpowiedź bez JSON-a — zostaje sam status */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export interface Health {
  status: string;
  db: string;
  schema_version: number | null;
  read_only: boolean;
  subjects: number;
}

export const getHealth = (signal?: AbortSignal) => fetchJson<Health>('/api/health', signal);

export const getDashboard = (signal?: AbortSignal) =>
  fetchJson<Dashboard>('/api/subjects', signal);

export const getSubject = (semester: number, skrot: string, grupa?: string, signal?: AbortSignal) =>
  fetchJson<SubjectDetail>(subjectUrl(semester, skrot, grupa), signal);

export const getItems = (filters: ItemFilters, signal?: AbortSignal) =>
  fetchJson<ItemsPage>(itemsUrl(filters), signal);

/** Szczegóły jednej treści — wszystkie kopie, relacje i nazwy, pod którymi leży (Q7). */
export interface ItemDetail {
  item: Item;
  files: Array<{ filename: string | null; source_relative_path: string | null; size_bytes: number | null }>;
  relations: Array<Record<string, unknown>>;
  /** Wszystkie nazwy tej treści, posortowane. Jedna treść bywa pod kilkunastoma. */
  names: string[];
  /** Najbardziej mówiąca z nich albo `null`, gdy nazwa jest tylko jedna. */
  suggested_name: string | null;
}

export const getItemDetail = (sha256: string, signal?: AbortSignal) =>
  fetchJson<ItemDetail>(`/api/items/${sha256}`, signal);

// --- S1: decisions ---

export interface DecisionRequest {
  sha256: string;
  decision_type: 'classify' | 'relation' | 'outdated' | 'skip' | 'quarantine';
  decided_by?: string;
  semester?: number;
  subject_key?: string;
  category?: string;
  target_relative_path?: string;
  action?: string;
  relation_override?: string;
  note?: string;
}

export interface DecisionResult {
  sha256: string;
  decision_type: string;
  decided_at: string;
}

export interface UndoResult {
  undone: Record<string, string>;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (data && typeof data.detail === 'string') detail = data.detail;
    } catch { /* no JSON */ }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const postDecision = (decision: DecisionRequest) =>
  postJson<DecisionResult>('/api/decisions', decision);

export const postDecisionBatch = (decisions: DecisionRequest[], decidedBy = 'studio') =>
  postJson<{ count: number; decisions: DecisionResult[] }>('/api/decisions/batch', {
    decisions,
    decided_by: decidedBy,
  });

export const postUndo = () => postJson<UndoResult>('/api/decisions/undo', {});

/** Wynik zmiany nazwy: `changed=false` znaczy „ta sama nazwa", więc nic nie zapisano. */
export interface RenameResult {
  sha256: string;
  old_path: string;
  target_relative_path: string;
  changed: boolean;
  decided_at: string | null;
}

/** Wynik zmiany nazwy pliku leżącego już w paczce (Q4): dysk i baza idą razem. */
export interface PackageRenameResult {
  old_path: string;
  target_relative_path: string;
  sha256: string;
  changed: boolean;
  /** Plan na dysku ma jeszcze starą ścieżkę — trzeba go zbudować od nowa. */
  plan_stale: boolean;
}

/**
 * Zmienia nazwę pliku, który JUŻ LEŻY w paczce: przenosi go na dysku i poprawia bazę
 * w jednej operacji. Dla pozycji dopiero zaplanowanych używa się `renameTarget` —
 * tam pliku na dysku jeszcze nie ma.
 */
export const renameInPackage = (targetRelativePath: string, filename: string) =>
  postJson<PackageRenameResult>('/api/package/rename', {
    target_relative_path: targetRelativePath,
    filename,
  });

/** Zmienia SAMĄ nazwę pliku docelowego; katalog zostaje. Kolizję zgłasza backend (409). */
export const renameTarget = (sha256: string, filename: string) =>
  postJson<RenameResult>('/api/decisions/rename', { sha256, filename });

// --- S1: preview + bulk ---

export interface Preview {
  sha256: string;
  content_kind: string | null;
  text_head: string | null;
  has_text: boolean;
  /** Język do kolorowania składni albo `null` — ustala backend, nie widok. */
  text_language: string | null;
  /** Czy pokazany tekst jest urwany — widok ma to powiedzieć, nie udawać całości. */
  text_truncated: boolean;
  has_image: boolean;
  /** Co widok ma narysować: 'page' (strona PDF), 'image', 'text', 'none'.
   *  Rodzaj ustala backend — front nie zgaduje po rozszerzeniu. */
  preview_kind: 'page' | 'image' | 'text' | 'none';
  has_thumbnail: boolean;
  pages: number | null;
  copies: number;
  source_path: string | null;
  ocr_done: boolean;
}

/**
 * Adres obrazka podglądu (strona PDF albo obraz). Przeglądarka pobiera go sama.
 *
 * `width` podaje się tam, gdzie rozmiar ma znaczenie: siatka klastra prosi o małe
 * miniatury (kilkanaście naraz), a porównanie dwóch zdjęć o coś, na czym widać różnicę.
 */
export function previewImageUrl(sha256: string, page = 1, width?: number): string {
  const size = width ? `&width=${width}` : '';
  return `/api/preview/${sha256}/image?page=${page}${size}`;
}

export interface FolderItems {
  folder: string;
  total: number;
  items: Item[];
  /** Katalogi powiązane ręcznie (Q3) — pokazywane ZAWSZE, dokładane tylko na żądanie. */
  linked_folders: string[];
  included_linked: boolean;
}

export interface FolderDecisionResult {
  folder: string;
  count: number;
  decisions: DecisionResult[];
}

export const getPreview = (sha256: string, signal?: AbortSignal) =>
  fetchJson<Preview>(`/api/preview/${sha256}`, signal);

export const getItemsByFolder = (folder: string, includeLinked = false, signal?: AbortSignal) =>
  fetchJson<FolderItems>(
    `/api/decisions/by-folder?folder=${encodeURIComponent(folder)}` +
      (includeLinked ? '&include_linked=true' : ''),
    signal,
  );

export const postDecisionByFolder = (folder: string, decisionType: string, extra: Record<string, unknown> = {}) =>
  postJson<FolderDecisionResult>('/api/decisions/by-folder', { folder, decision_type: decisionType, ...extra });

// --- Q3: katalogi i ich ręczne powiązania ---

export interface FolderRow {
  folder_path: string;
  source_package: string;
  file_count: number | null;
  total_bytes: number | null;
  /** Automatyczny dedup (równość poddrzewa co do bitu) — co innego niż powiązanie ręczne. */
  duplicate_of: string | null;
  /** Katalogi powiązane RĘCZNIE, z obu stron pary. */
  linked_to: string[];
}

export interface FoldersPage {
  total: number;
  limit: number;
  offset: number;
  folders: FolderRow[];
}

export interface FolderLink {
  folder_a: string;
  folder_b: string;
  kind: 'duplicate' | 'related';
  decided_by: string;
  decided_at: string;
  note: string | null;
}

export const getFolders = (
  filters: { q?: string; package?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<FoldersPage>(`/api/folders${query ? `?${query}` : ''}`, signal);
};

export const getFolderLinks = (folder?: string, signal?: AbortSignal) =>
  fetchJson<{ total: number; links: FolderLink[] }>(
    `/api/folders/links${folder ? `?folder=${encodeURIComponent(folder)}` : ''}`,
    signal,
  );

export const linkFolders = (
  folderA: string,
  folderB: string,
  kind: 'duplicate' | 'related' = 'duplicate',
  note?: string,
) => postJson<FolderLink>('/api/folders/links', {
  folder_a: folderA, folder_b: folderB, kind, note,
});

/** DELETE z parametrami w adresie — para jest kluczem, nie treścią żądania. */
export const unlinkFolders = async (folderA: string, folderB: string) => {
  const params = new URLSearchParams({ folder_a: folderA, folder_b: folderB });
  const response = await fetch(`/api/folders/links?${params}`, {
    method: 'DELETE',
    headers: { accept: 'application/json' },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (data && typeof data.detail === 'string') detail = data.detail;
    } catch { /* odpowiedź bez JSON-a */ }
    throw new Error(detail);
  }
  return (await response.json()) as { unlinked: { folder_a: string; folder_b: string } };
};

// --- S2: clusters ---

export interface ClusterRelation {
  source_sha256: string;
  target_sha256: string;
  relation_type: string;
  confidence: number;
  detection_method: string;
  reason: string;
}

export interface Cluster {
  members: Item[];
  relations: ClusterRelation[];
  size: number;
  strength: number;
  has_older_version: boolean;
}

export interface ClustersPage {
  total: number;
  clusters: Cluster[];
}

export interface ResolveResult {
  canonical: string;
  skipped: number;
  decisions: DecisionResult[];
}

export const getClusters = (
  filters: { semester?: number; skrot?: string; noise?: string } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<ClustersPage>(query ? `/api/clusters?${query}` : '/api/clusters', signal);
};

export interface ClusterDiff {
  left: Item;
  right: Item;
  left_text: string | null;
  right_text: string | null;
  diff_type: 'text' | 'meta';
  relation: ClusterRelation | null;
}

export const getClusterDiff = (leftSha: string, rightSha: string, signal?: AbortSignal) =>
  fetchJson<ClusterDiff>(`/api/clusters/diff?left=${leftSha}&right=${rightSha}`, signal);

/** Treść w podpowiedzi „chyba jedna sesja" (Q8). */
export interface SessionContent {
  sha256: string;
  filename: string | null;
  source_relative_path: string | null;
  size_bytes: number | null;
  category: string | null;
  semester: number | null;
  subject_key: string | null;
  confidence: number | null;
  action: string | null;
  needs_review: number | null;
}

export interface SessionGroup {
  folder: string;
  day: string;
  contents: SessionContent[];
}

/**
 * Treści z jednego katalogu i jednego dnia. Podpowiedź pokazuje się TYLKO tam, gdzie data
 * naprawdę rozdziela katalog — w większości katalogów jest to data skopiowania paczki.
 */
export const getSameDayGroups = (
  filters: { semester?: number; skrot?: string; max_size?: number } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<{ total: number; limit: number; groups: SessionGroup[] }>(
    `/api/clusters/same-day${query ? `?${query}` : ''}`,
    signal,
  );
};

export const resolveCluster = (canonicalSha256: string, members: string[], decidedBy = 'studio') =>
  postJson<ResolveResult>('/api/clusters/resolve', {
    canonical_sha256: canonicalSha256,
    members,
    decided_by: decidedBy,
  });

/** Rodzaj scalenia: „ten sam materiał" albo „to jest starsza wersja tamtego". */
export type MergeRelation = 'near_duplicate' | 'older_version';

export interface MergeResult {
  canonical: string;
  merged: number;
  relation: MergeRelation;
}

/**
 * Scala treści w jedną kanoniczną: wchłonięte dostają `skip`, a powiązanie ląduje
 * w `relations` — czyli tam, gdzie widzi je graf i raporty, nie tylko w notatce.
 */
export const mergeContents = (
  canonicalSha256: string,
  absorbed: string[],
  relation: MergeRelation = 'near_duplicate',
  decidedBy = 'studio',
) =>
  postJson<MergeResult>('/api/decisions/merge', {
    canonical_sha256: canonicalSha256,
    absorbed,
    relation,
    decided_by: decidedBy,
  });

/** Treść walcząca o ścieżkę — tyle, żeby dało się wybrać bez wchodzenia w każdą z osobna. */
export interface ConflictContent {
  sha256: string;
  filename: string | null;
  source_relative_path: string | null;
  size_bytes: number | null;
  confidence: number | null;
  classification_method: string | null;
  category: string | null;
  needs_review: number | null;
}

export interface PlanConflict {
  /** `plan` — dwie zaplanowane treści; `applied` — zderzenie z tym, co leży w paczce. */
  kind: 'plan' | 'applied';
  path: string;
  applied_sha256: string | null;
  contents: ConflictContent[];
}

export interface PlanConflicts {
  total: number;
  conflicts: PlanConflict[];
}

/** Konflikty liczone z bazy, nie z pliku planu — zmiana nazwy gasi je od razu. */
export const getPlanConflicts = (
  filters: { semester?: number; skrot?: string } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<PlanConflicts>(`/api/plan/conflicts${query ? `?${query}` : ''}`, signal);
};

export const getQueue = (filters: { semester?: number; skrot?: string; limit?: number } = {}, signal?: AbortSignal) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<ItemsPage>(query ? `/api/queue?${query}` : '/api/queue', signal);
};

// --- S4: history, search, stats ---

export interface ManualDecision {
  sha256: string;
  decision_type: string;
  target_relative_path: string | null;
  relation_override: string | null;
  decided_by: string;
  decided_at: string;
  note: string | null;
}

export interface HistoryPage {
  total: number;
  limit: number;
  offset: number;
  decisions: ManualDecision[];
}

export interface SearchResult {
  query: string;
  total: number;
  items: Item[];
}

export interface LiveStats {
  thresholds: Thresholds;
  totals: Totals & { manual_decisions: number };
  stages: Record<string, number>;
  methods: Record<string, number>;
  categories: Record<string, number>;
  actions: Record<string, number>;
}

export const getHistory = (
  filters: { decided_by?: string; since?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return fetchJson<HistoryPage>(query ? `/api/decisions/history?${query}` : '/api/decisions/history', signal);
};

export const deleteDecision = (sha256: string) =>
  fetch(`/api/decisions/${sha256}`, { method: 'DELETE', headers: { accept: 'application/json' } })
    .then(async (r) => {
      if (!r.ok) {
        let detail = `${r.status}`;
        try { const b = await r.json(); if (b?.detail) detail = b.detail; } catch {}
        throw new Error(detail);
      }
      return r.json() as Promise<{ undone: ManualDecision }>;
    });

export const searchItems = (q: string, limit = 50, signal?: AbortSignal) =>
  fetchJson<SearchResult>(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`, signal);

export const getStats = (signal?: AbortSignal) =>
  fetchJson<LiveStats>('/api/stats', signal);


// --- S4.1: graf jako soczewka ---------------------------------------------

export interface GraphStatus {
  viewer_built: boolean;
  graph_json: string | null;
  notes: number;
  hint: string;
}

export interface GraphNodeRef {
  sha256: string;
  nodes: string[];
  url: string;
}

export interface GraphSubjectRef {
  node: string;
  url: string;
}

export interface GraphContentRef {
  node: string;
  candidates: string[];
  sha256: string | null;
  item: Item | null;
}

export const getGraphStatus = (signal?: AbortSignal) =>
  fetchJson<GraphStatus>('/api/graph/status', signal);

/** Węzeł grafu odpowiadający treści (kierunek: studio → graf). */
export const getGraphNodeFor = (sha256: string, signal?: AbortSignal) =>
  fetchJson<GraphNodeRef>(`/api/graph/node/${sha256}`, signal);

/** Węzeł przedmiotu — wejście do grafu z listy przedmiotów. */
export const getGraphSubject = (semester: number, skrot: string, grupa?: string, signal?: AbortSignal) =>
  fetchJson<GraphSubjectRef>(
    `/api/graph/subject/${semester}/${encodeURIComponent(skrot)}` +
      (grupa ? `?grupa=${encodeURIComponent(grupa)}` : ''),
    signal,
  );

/** Treść pokazywana przez węzeł (kierunek: graf → studio). */
export const getGraphContent = (node: string, signal?: AbortSignal) =>
  fetchJson<GraphContentRef>(`/api/graph/content/${encodeURIComponent(node)}`, signal);

/** Adres osadzanego viewera z zaznaczonym węzłem. */
export function graphUrl(node?: string | null): string {
  return node ? `/graf/#${node}` : '/graf/';
}


// --- S3: plan, bramka i wykonanie ------------------------------------------

export interface PlanFinding {
  level: string;
  code: string;
  message: string;
  source_sha256: string | null;
  target_rel: string | null;
}

export interface PlanOverview {
  subject: { semester: number; skrot: string; nazwa: string; grupa: string; target_dir: string };
  plan: {
    path: string;
    plan_hash: string;
    declared_hash: string;
    created_at: string;
    items: number;
    actions: Record<string, number>;
    needs_review: number;
  } | null;
  validation?: {
    errors: number;
    warnings: number;
    blocking: number;
    findings: PlanFinding[];
    truncated: number;
  };
  diff?: {
    files: number;
    folders: number;
    new: number;
    present: number;
    conflict: number;
    missing_source: number;
    outside: number;
    blockers: Array<{ state: string; target_rel: string; detail: string; sha256: string }>;
  };
  can_apply: boolean;
  reason: string;
}

export interface TreeFile {
  name: string;
  path: string;
  state: 'new' | 'present' | 'conflict' | 'missing_source' | 'outside' | 'ground_truth';
  sha256: string;
  detail: string;
}

export interface PlanTree {
  target_dir: string;
  folders: Array<{ path: string; files: TreeFile[]; states: Record<string, number> }>;
  files: number;
  homeless: Array<{
    sha256: string;
    /** Nazwa pliku — „przenieś tu” składa z niej ścieżkę docelową. */
    filename: string;
    action: string | null;
    category: string | null;
    reason: string | null;
    confidence: number | null;
    needs_review: boolean;
    target_rel: string | null;
  }>;
}

/** Etapy, które studio umie uruchomić jako podproces CLI. */
export type Stage = 'plan' | 'validate' | 'review' | 'apply-dry' | 'apply' | 'verify';

export const getPlan = (semester: number, skrot: string, grupa?: string, signal?: AbortSignal) =>
  fetchJson<PlanOverview>(
    `/api/plan/${semester}/${encodeURIComponent(skrot)}` + (grupa ? `?grupa=${encodeURIComponent(grupa)}` : ''),
    signal,
  );

export const getPlanTree = (semester: number, skrot: string, grupa?: string, signal?: AbortSignal) =>
  fetchJson<PlanTree>(
    `/api/plan/${semester}/${encodeURIComponent(skrot)}/tree` +
      (grupa ? `?grupa=${encodeURIComponent(grupa)}` : ''),
    signal,
  );

/**
 * Uruchamia etap i oddaje jego wyjście linia po linii, na żywo.
 *
 * Strumień idzie POST-em (EventSource umie tylko GET), a odmowa bramki wraca
 * zwykłym kodem 409 ZANIM cokolwiek wystartuje — widok ma ją pokazać, a nie
 * tłumaczyć „coś poszło nie tak”.
 */
/** Treść błędu z odpowiedzi API — backend wkłada powód do `detail`. */
async function failure(response: Response): Promise<Error> {
  let detail: unknown = `${response.status} ${response.statusText}`;
  try {
    detail = (await response.json()).detail ?? detail;
  } catch {
    /* odpowiedź bez JSON-a */
  }
  return new Error(typeof detail === 'string' ? detail : JSON.stringify(detail, null, 1));
}

/**
 * Czyta strumień SSE etapu i oddaje jego KOD WYJŚCIA.
 *
 * To kod, a nie treść logu, mówi widokowi, czy się udało — log bywa pełen ostrzeżeń
 * przy udanym przebiegu i pusty przy nieudanym.
 */
async function readStageStream(
  response: Response,
  onLine: (line: string) => void,
): Promise<number> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('przeglądarka nie oddała strumienia');
  const decoder = new TextDecoder();
  let buffer = '';
  let code = -1;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() ?? '';
    for (const chunk of chunks) {
      const event = /^event: (\w+)/m.exec(chunk)?.[1];
      const data = /^data: (.*)$/m.exec(chunk)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === 'line') onLine(payload.text);
      else if (event === 'start') onLine(`$ ${payload.argv.slice(1).join(' ')}`);
      else if (event === 'done') code = payload.code;
    }
  }
  return code;
}

/**
 * Przebudowa DANYCH grafu: eksport vaulta z bazy i generator.
 *
 * Graf jest migawką, więc bez tego decyzja podjęta w studiu nie jest w nim widoczna.
 * Paczki JS viewera się nie buduje — czyta on `graph.json` przy starcie.
 */
export async function rebuildGraph(onLine: (line: string) => void): Promise<number> {
  const response = await fetch('/api/graph/rebuild', { method: 'POST' });
  if (!response.ok) throw await failure(response);
  return readStageStream(response, onLine);
}

export async function runStage(
  semester: number,
  skrot: string,
  body: { stage: Stage; plan_hash?: string; confirm?: boolean },
  onLine: (line: string) => void,
  grupa?: string,
): Promise<number> {
  const response = await fetch(
    `/api/plan/${semester}/${encodeURIComponent(skrot)}/run` +
      (grupa ? `?grupa=${encodeURIComponent(grupa)}` : ''),
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!response.ok) throw await failure(response);
  return readStageStream(response, onLine);
}
