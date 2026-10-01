/**
 * Wspólna warstwa transportowa klienta API: opakowania na `fetch`, powód błędu
 * z `detail` i czytanie strumienia SSE etapu. Nic z tego nie wychodzi na zewnątrz
 * `lib/api/` — `index.ts` eksportuje tylko to, co widok naprawdę wywołuje.
 */

export async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
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

export async function postJson<T>(url: string, body: unknown): Promise<T> {
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

/** Treść błędu z odpowiedzi API — backend wkłada powód do `detail`. */
export async function failure(response: Response): Promise<Error> {
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
export async function readStageStream(
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
