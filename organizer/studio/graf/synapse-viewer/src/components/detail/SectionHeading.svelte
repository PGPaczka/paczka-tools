<script lang="ts">
  /**
   * Nagłówek sekcji panelu. Sekcje notatki pliku odpowiadają na różne pytania — co to
   * jest, gdzie trafi, skąd się wzięło — i bez wspólnego nagłówka zlewały się w jedną
   * kolumnę drobnego tekstu (zgłoszone 2026-09-30).
   */
  export let title: string
  /** Drobny dopisek obok tytułu: licznik, tryb — to, co doprecyzowuje sekcję. */
  export let note: string = ''
</script>

<div class="head">
  <span class="title">{title}</span>
  {#if note}<span class="note">{note}</span>{/if}
</div>

<style>
  .head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin: 0 0 8px;
  }
  .title {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.11em;
    text-transform: uppercase;
    color: var(--muted);
    white-space: nowrap;
  }
  .note {
    font-size: 11px;
    color: var(--muted-2);
    white-space: nowrap;
  }
</style>
