/**
 * Graf jako soczewka: `/api/graph/*` w obie strony (studio → węzeł, węzeł → treść)
 * i przebudowa jego DANYCH.
 */

import { failure, fetchJson, readStageStream } from './_client';
import type { Item } from './items';

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

/** Przedmiot stojący za id węzła grafu — wejście z macierzy pokrycia w pracę. */
export interface GraphScope {
  semester: number;
  skrot: string;
  grupa: string;
}

export const getGraphScope = (nodeId: string, signal?: AbortSignal) =>
  fetchJson<GraphScope>(`/api/graph/scope/${encodeURIComponent(nodeId)}`, signal);
