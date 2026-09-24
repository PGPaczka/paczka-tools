<script lang="ts">
  /**
   * Ręczne powiązanie dwóch katalogów między paczkami (Q3).
   *
   * Dedup katalogów jest automatyczny i dokładny (`duplicate_of` z `tree_hash`), więc
   * widzi tylko poddrzewa identyczne co do bitu. Tutaj człowiek mówi to, czego maszyna
   * nie widzi: „to jest ten sam materiał, choć pliki się różnią". Dlatego obie strony
   * mają PODGLĄD zawartości — powiązanie bez zajrzenia do środka to zgadywanie.
   */
  import {
    getFolders,
    getFolderLinks,
    getItemsByFolder,
    linkFolders,
    unlinkFolders,
    type FolderRow,
    type FolderLink,
    type FolderItems,
  } from '../lib/api';
  import { bytes, count } from '../lib/format';

  type Side = 'a' | 'b';

  let queryA = $state('');
  let queryB = $state('');
  let foldersA = $state<FolderRow[]>([]);
  let foldersB = $state<FolderRow[]>([]);
  let pickedA = $state<FolderRow | null>(null);
  let pickedB = $state<FolderRow | null>(null);
  let previewA = $state<FolderItems | null>(null);
  let previewB = $state<FolderItems | null>(null);

  let links = $state<FolderLink[]>([]);
  let kind = $state<'duplicate' | 'related'>('duplicate');
  let note = $state('');
  let error = $state<string | null>(null);
  let success = $state<string | null>(null);
  let busy = $state(false);

  const ready = $derived(
    pickedA !== null && pickedB !== null && pickedA.folder_path !== pickedB.folder_path,
  );

  async function search(side: Side, q: string): Promise<void> {
    try {
      const page = await getFolders({ q: q.trim() || undefined, limit: 40 });
      if (side === 'a') foldersA = page.folders;
      else foldersB = page.folders;
      error = null;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function pick(side: Side, folder: FolderRow): Promise<void> {
    if (side === 'a') {
      pickedA = folder;
      previewA = null;
    } else {
      pickedB = folder;
      previewB = null;
    }
    try {
      // Podgląd to pierwsze pozycje katalogu — tyle, żeby rozpoznać materiał.
      const page = await getItemsByFolder(folder.folder_path);
      if (side === 'a') previewA = page;
      else previewB = page;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function loadLinks(): Promise<void> {
    try {
      links = (await getFolderLinks()).links;
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  async function save(): Promise<void> {
    if (!ready || busy) return;
    busy = true;
    error = null;
    try {
      await linkFolders(pickedA!.folder_path, pickedB!.folder_path, kind, note.trim() || undefined);
      success = `powiązane: ${pickedA!.folder_path} ↔ ${pickedB!.folder_path}`;
      note = '';
      await Promise.all([loadLinks(), search('a', queryA), search('b', queryB)]);
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    } finally {
      busy = false;
    }
  }

  async function remove(link: FolderLink): Promise<void> {
    error = null;
    try {
      await unlinkFolders(link.folder_a, link.folder_b);
      success = 'powiązanie usunięte';
      await Promise.all([loadLinks(), search('a', queryA), search('b', queryB)]);
    } catch (exc) {
      error = exc instanceof Error ? exc.message : String(exc);
    }
  }

  // Pierwsze wypełnienie list. Bez zależności reaktywnych: szukaniem steruje `oninput`.
  $effect(() => {
    search('a', '');
    search('b', '');
    loadLinks();
  });
</script>

<section class="folder-links">
  <header>
    <h3>Powiąż katalogi</h3>
    <p class="dim">
      Automatyczny dedup łączy tylko katalogi identyczne co do bitu. Tutaj powiesz, że dwa
      katalogi to ten sam materiał, choć pliki się różnią. Powiązanie niczego nie kasuje
      ani nie wyłącza z potoku — jest podpowiedzią przy decyzjach.
    </p>
  </header>

  {#if error}<p class="error">{error}</p>{/if}
  {#if success}<p class="ok">{success}</p>{/if}

  <div class="sides">
    {#each [{ side: 'a' as Side, folders: foldersA, picked: pickedA, preview: previewA }, { side: 'b' as Side, folders: foldersB, picked: pickedB, preview: previewB }] as column (column.side)}
      <div class="side">
        <input
          class="mono"
          placeholder={column.side === 'a' ? 'szukaj katalogu…' : 'szukaj drugiego katalogu…'}
          value={column.side === 'a' ? queryA : queryB}
          oninput={(e) => {
            const value = (e.currentTarget as HTMLInputElement).value;
            if (column.side === 'a') queryA = value;
            else queryB = value;
            search(column.side, value);
          }}
        />

        <div class="folder-list">
          {#each column.folders as folder (folder.folder_path)}
            <button
              class="folder"
              class:picked={column.picked?.folder_path === folder.folder_path}
              onclick={() => pick(column.side, folder)}
            >
              <span class="mono path">{folder.folder_path}</span>
              <span class="dim num">{count(folder.file_count ?? 0)} plików</span>
              {#if folder.total_bytes}<span class="dim">{bytes(folder.total_bytes)}</span>{/if}
              {#if folder.duplicate_of}
                <span class="tag auto" title="automatyczny dedup: {folder.duplicate_of}">dup</span>
              {/if}
              {#if folder.linked_to.length}
                <span class="tag manual" title={folder.linked_to.join('\n')}>
                  powiązany ×{folder.linked_to.length}
                </span>
              {/if}
            </button>
          {/each}
          {#if !column.folders.length}
            <p class="empty dim">Nic nie pasuje.</p>
          {/if}
        </div>

        {#if column.picked}
          <div class="preview">
            <div class="mono dim">{column.picked.folder_path}</div>
            {#if column.preview}
              <div class="dim">{count(column.preview.total)} pozycji</div>
              <ul>
                {#each column.preview.items.slice(0, 8) as item (item.sha256)}
                  <li class="mono">{item.filename ?? item.sha256.slice(0, 12)}</li>
                {/each}
              </ul>
              {#if column.preview.total > 8}<div class="dim">…</div>{/if}
            {:else}
              <div class="dim">Wczytuję zawartość…</div>
            {/if}
          </div>
        {/if}
      </div>
    {/each}
  </div>

  <div class="actions">
    <label class="dim">
      rodzaj
      <select bind:value={kind}>
        <option value="duplicate">ten sam materiał</option>
        <option value="related">powiązane</option>
      </select>
    </label>
    <input class="note" placeholder="notatka (opcjonalnie)" bind:value={note} />
    <button class="save" disabled={!ready || busy} onclick={save}>
      {busy ? 'zapisuję…' : 'powiąż'}
    </button>
    {#if !ready}
      <span class="dim">wybierz po jednym katalogu z każdej kolumny</span>
    {/if}
  </div>

  <div class="existing">
    <h4>Powiązania <span class="num dim">{count(links.length)}</span></h4>
    {#each links as link (link.folder_a + link.folder_b)}
      <div class="link-row">
        <span class="mono">{link.folder_a}</span>
        <span class="dim">↔</span>
        <span class="mono">{link.folder_b}</span>
        <span class="tag">{link.kind === 'duplicate' ? 'ten sam materiał' : 'powiązane'}</span>
        {#if link.note}<span class="dim note-text">{link.note}</span>{/if}
        <button class="ghost" onclick={() => remove(link)}>rozwiąż</button>
      </div>
    {/each}
    {#if !links.length}
      <p class="empty dim">Jeszcze nic nie powiązano ręcznie.</p>
    {/if}
  </div>
</section>

<style>
  .folder-links {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 0;
    padding: 14px 16px 24px;
    overflow-y: auto;
  }
  header p {
    margin: 4px 0 0;
    max-width: 62ch;
    font-size: 11px;
    line-height: 1.5;
  }
  .sides {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  /* Na telefonie dwie kolumny katalogów to dwie kolumny obciętych ścieżek — a ścieżka
     jest tu jedyną informacją, po której człowiek rozpoznaje katalog. */
  @media (max-width: 800px) {
    .sides {
      grid-template-columns: 1fr;
    }
  }
  .side {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .side input {
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--bg-deep);
    color: var(--text);
    font-size: 12px;
  }
  .folder-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
    max-height: 34vh;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px;
  }
  .folder {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 3px 6px;
    border: 1px solid transparent;
    border-radius: 4px;
    background: transparent;
    color: var(--text);
    font-size: 11px;
    text-align: left;
    cursor: pointer;
  }
  .folder:hover {
    background: var(--panel);
  }
  .folder.picked {
    border-color: var(--accent-dim);
    background: var(--panel);
  }
  .folder .path {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tag.auto {
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 0 6px;
    font-size: 9px;
  }
  .tag.manual {
    color: var(--bg-deep);
    background: var(--accent-dim);
    border-radius: 999px;
    padding: 0 6px;
    font-size: 9px;
  }
  .preview {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 11px;
  }
  .preview ul {
    margin: 4px 0 0;
    padding-left: 16px;
  }
  .preview li {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 11px;
  }
  .actions select,
  .actions .note {
    padding: 3px 8px;
    border: 1px solid var(--border);
    border-radius: 5px;
    background: var(--bg-deep);
    color: var(--text);
    font-size: 11px;
  }
  .actions .note {
    flex: 1 1 14rem;
    min-width: 8rem;
  }
  .save {
    padding: 3px 14px;
    border: 1px solid var(--accent-dim);
    border-radius: 999px;
    background: transparent;
    color: var(--text);
    font-size: 11px;
    cursor: pointer;
  }
  .save:disabled {
    opacity: 0.5;
    cursor: default;
    border-color: var(--border);
    color: var(--muted);
  }
  .existing {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .existing h4 {
    margin: 0;
    font-size: 12px;
  }
  .link-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 11px;
  }
  .link-row .note-text {
    flex: 1 1 8rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .ghost {
    padding: 1px 8px;
    border: 1px solid transparent;
    border-radius: 999px;
    background: transparent;
    color: var(--muted);
    font-size: 10px;
    cursor: pointer;
  }
  .ghost:hover {
    color: var(--text);
    border-color: var(--border);
  }
  .empty {
    padding: 6px;
    font-size: 11px;
  }
  .error {
    color: var(--red);
    font-size: 11px;
  }
  .ok {
    color: var(--green);
    font-size: 11px;
  }
</style>
