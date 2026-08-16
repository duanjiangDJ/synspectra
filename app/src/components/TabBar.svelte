<script lang="ts">
  import { t } from "../lib/i18n";

  interface Tab {
    id: string;
    labelKey: string;
  }

  let {
    tabs,
    active,
    onSelect,
  }: {
    tabs: Tab[];
    active: string;
    onSelect: (id: string) => void;
  } = $props();
</script>

<nav class="tabbar" aria-label="tabs">
  {#each tabs as tab (tab.id)}
    <button
      type="button"
      class="tab"
      class:active={active === tab.id}
      onclick={() => onSelect(tab.id)}
    >
      {$t(tab.labelKey)}
    </button>
  {/each}
</nav>
