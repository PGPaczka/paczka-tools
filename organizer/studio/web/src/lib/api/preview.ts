/** Podgląd treści: `/api/preview/{sha256}` i adres obrazka strony. */

import { fetchJson } from './_client';

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

export const getPreview = (sha256: string, signal?: AbortSignal) =>
  fetchJson<Preview>(`/api/preview/${sha256}`, signal);
