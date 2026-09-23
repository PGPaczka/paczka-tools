<script lang="ts">
  /**
   * Podgląd pliku, którego nie da się pokazać obrazkiem: md, txt, kod, XML projektu.
   *
   * Powstał po zgłoszeniu z telefonu, że przy takich pozycjach panel był pusty —
   * a decyzja „zostaw / duplikat / inna ścieżka" zapada po tym, CZYM plik jest.
   * Kolorowanie składni jest nadbudową: gdy go nie ma, widać czysty tekst.
   */
  import { highlight } from '../lib/highlight';

  interface Props {
    text: string;
    /** Język z backendu (`preview.text_language`); `null` = zwykły tekst. */
    language?: string | null;
    /** Nazwa pliku i rodzaj treści — podpis nad tekstem, żeby wiadomo było, co to. */
    label?: string | null;
  }

  let { text, language = null, label = null }: Props = $props();

  let html = $state<string | null>(null);

  $effect(() => {
    const snapshotText = text;
    const snapshotLanguage = language;
    html = null;
    void highlight(snapshotText, snapshotLanguage).then((value) => {
      // Podgląd bywa przełączany szybciej, niż doczyta się biblioteka.
      if (snapshotText === text && snapshotLanguage === language) html = value;
    });
  });
</script>

<div class="text-preview">
  {#if label || language}
    <div class="caption">
      {#if label}<span class="name">{label}</span>{/if}
      {#if language && language !== 'plaintext'}<span class="lang">{language}</span>{/if}
    </div>
  {/if}
  <pre class="text-head"><code class="hljs"
      >{#if html}{@html html}{:else}{text}{/if}</code
    ></pre>
</div>

<style>
  .text-preview {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    width: 100%;
  }
  .caption {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--muted);
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .lang {
    flex: none;
    padding: 0 6px;
    border: 1px solid var(--border);
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 10px;
  }
  .text-head {
    margin: 0;
    max-height: 44vh;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.55;
    color: var(--text);
  }
  .text-head :global(.hljs) {
    background: transparent;
    padding: 0;
  }
</style>
