/**
 * Pomocnicze wyliczenia widoku planu (S3.2). Żadnej reguły klasyfikacji tu nie ma —
 * ścieżkę docelową składamy z katalogu wybranego w drzewie i nazwy pliku, a kolizję
 * rozstrzygamy po tym, co backend już policzył i przysłał w drzewie.
 */

import type { PlanTree, TreeFile } from './api';

/** Ścieżka, pod którą wylądowałaby pozycja po „przenieś tu”. */
export function moveTarget(folder: string | null, filename: string | null): string | null {
  if (!folder || !filename) return null;
  return `${folder.replace(/\/+$/, '')}/${filename}`;
}

/**
 * Plik, który już stoi pod tą ścieżką — albo `null`.
 *
 * Kolizja nazw nie jest ostrzeżeniem kosmetycznym: dwie treści pod jedną ścieżką
 * zatrzymują bramkę planu, więc lepiej pokazać to przy wyborze katalogu niż
 * przy `apply`.
 */
export function collisionAt(tree: PlanTree | null, path: string | null): TreeFile | null {
  if (!tree || !path) return null;
  for (const folder of tree.folders) {
    const hit = folder.files.find((file) => file.path === path);
    if (hit) return hit;
  }
  return null;
}
