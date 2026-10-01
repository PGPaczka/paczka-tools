/**
 * Decyzje ręczne: `/api/decisions`, jej wariant hurtowy, cofnięcie i zmiany nazw
 * (`/api/decisions/rename`, `/api/package/rename`).
 */

import { postJson } from './_client';

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
