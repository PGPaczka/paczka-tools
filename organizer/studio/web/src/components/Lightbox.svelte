<script lang="ts">
  /**
   * Podgląd na cały ekran. Powstał, bo miniatura odpowiada na pytanie „co to jest”,
   * ale nie na „czym te dwa skany się różnią” — a to drugie jest sednem pracy nad
   * duplikatami.
   *
   * Obraz pobieramy w większej rozdzielczości niż w siatce (ten sam endpoint, inne
   * `width`), a nie skalujemy miniatury: rozmazany podgląd nie rozstrzyga niczego.
   */
  interface Props {
    src: string;
    alt?: string;
    caption?: string | null;
    /** Adres oryginału — „otwórz w nowej karcie”, gdzie działa zoom przeglądarki. */
    original?: string | null;
    onClose: () => void;
  }

  let { src, alt = 'Podgląd', caption = null, original = null, onClose }: Props = $props();

  let loaded = $state(false);

  function onKey(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onClose();
    }
  }
</script>

<svelte:window onkeydown={onKey} />

<!-- Kliknięcie tła zamyka; kliknięcie samego obrazu nie, żeby dało się go dotykać. -->
<div
  class="backdrop"
  role="button"
  tabindex="0"
  aria-label="Zamknij podgląd"
  onclick={onClose}
  onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onClose()}
>
  <figure onclick={(e) => e.stopPropagation()} role="presentation">
    {#if !loaded}<div class="loading">Wczytuję podgląd…</div>{/if}
    <img {src} {alt} onload={() => (loaded = true)} class:hidden={!loaded} />
    <figcaption>
      <span class="name">{caption ?? alt}</span>
      {#if original}
        <a href={original} target="_blank" rel="noreferrer">otwórz oryginał ↗</a>
      {/if}
      <button onclick={onClose}>zamknij (Esc)</button>
    </figcaption>
  </figure>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    background: rgba(1, 4, 9, 0.92);
    cursor: zoom-out;
  }
  figure {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 0;
    max-width: 100%;
    max-height: 100%;
    cursor: default;
  }
  img {
    max-width: 100%;
    /* Zostawiamy miejsce na podpis; `contain` bo liczy się cały kadr. */
    max-height: calc(100vh - 90px);
    object-fit: contain;
    border-radius: 6px;
    background: #fff;
  }
  img.hidden {
    display: none;
  }
  .loading {
    padding: 40px 60px;
    color: var(--muted);
    text-align: center;
  }
  figcaption {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    color: var(--muted);
    font-size: 12px;
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
  }
  figcaption a,
  figcaption button {
    padding: 3px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    color: var(--muted);
    text-decoration: none;
    white-space: nowrap;
  }
  figcaption a:hover,
  figcaption button:hover {
    color: var(--text);
    border-color: var(--accent-dim);
  }
</style>
