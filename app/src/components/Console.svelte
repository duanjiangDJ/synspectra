<script lang="ts">
  import { t } from "../lib/i18n";
  import { formatConsoleLine, type ConsoleEntry } from "../lib/console";

  let { lines }: { lines: string[] } = $props();
  let box = $state<HTMLDivElement>();

  const entries = $derived<ConsoleEntry[]>(lines.map((line, index) => formatConsoleLine(line, index)));

  $effect(() => {
    if (box) {
      box.scrollTop = box.scrollHeight;
    }
  });
</script>

<div bind:this={box} class="console-box" aria-live="polite">
  {#if entries.length === 0}
    <span class="console-empty">{$t("console.empty")}</span>
  {:else}
    {#each entries as entry (entry.id)}
      <div class="console-line console-{entry.level}">
        <span class="console-prefix">{entry.prefix}</span>
        <span class="console-text">{entry.text}</span>
      </div>
    {/each}
  {/if}
</div>
