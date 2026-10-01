/**
 * Klient API studia, zebrany w jedno wejście. Typy odpowiadają kształtowi
 * z `studio/api/queries.py`; widok niczego nie dolicza — jeśli jakiejś liczby tu nie ma,
 * ma ją dodać backend (studio/AGENTS.md, reguła 1).
 *
 * Moduły dzielą się po rodzinach endpointów; `_client.ts` trzyma wspólny transport
 * i NIE jest częścią publicznego wejścia. Nazwy wypisane są jawnie, żeby po tej
 * liście było widać, czego widok naprawdę używa.
 */

// pulpit i przedmioty
export { subjectUrl, getHealth, getDashboard, getSubject } from './dashboard';
export type {
  Thresholds,
  Totals,
  SubjectRow,
  QueueStage,
  Dashboard,
  CategoryRow,
  SubjectDetail,
  Health,
} from './dashboard';

// pozycje, kolejka, wyszukiwanie
export { itemsUrl, getItems, getItemDetail, getQueue, searchItems } from './items';
export type { Item, ItemsPage, ItemFilters, ItemDetail, SearchResult } from './items';

// decyzje ręczne i zmiany nazw
export {
  postDecision,
  postDecisionBatch,
  postUndo,
  renameInPackage,
  renameTarget,
} from './decisions';
export type {
  DecisionRequest,
  DecisionResult,
  UndoResult,
  RenameResult,
  PackageRenameResult,
} from './decisions';

// podgląd treści
export { previewImageUrl, getPreview } from './preview';
export type { Preview } from './preview';

// katalogi i ich powiązania
export {
  getItemsByFolder,
  postDecisionByFolder,
  getFolders,
  getFolderLinks,
  linkFolders,
  unlinkFolders,
} from './folders';
export type {
  FolderItems,
  FolderDecisionResult,
  FolderRow,
  FoldersPage,
  FolderLink,
} from './folders';

// klastry powtórzeń i scalanie
export {
  getClusters,
  getClusterDiff,
  getSameDayGroups,
  resolveCluster,
  mergeContents,
} from './clusters';
export type {
  ClusterRelation,
  Cluster,
  ClustersPage,
  ResolveResult,
  ClusterDiff,
  SessionContent,
  SessionGroup,
  MergeRelation,
  MergeResult,
} from './clusters';

// plan, bramka, etapy
export {
  getPlanConflicts,
  getPlan,
  getPlanTree,
  getPipeline,
  runIndexStage,
  runStage,
} from './plan';
export type {
  ConflictContent,
  PlanConflict,
  PlanConflicts,
  PlanFinding,
  PlanOverview,
  TreeFile,
  PlanTree,
  Stage,
  IndexStage,
  PipelineState,
} from './plan';

// graf jako soczewka
export {
  getGraphStatus,
  getGraphNodeFor,
  getGraphSubject,
  getGraphContent,
  graphUrl,
  rebuildGraph,
  getGraphScope,
} from './graph';
export type {
  GraphStatus,
  GraphNodeRef,
  GraphSubjectRef,
  GraphContentRef,
  GraphScope,
} from './graph';

// historia decyzji
export { getHistory, deleteDecision } from './history';
export type { ManualDecision, HistoryPage } from './history';

// liczby na żywo
export { getStats } from './stats';
export type { LiveStats } from './stats';
