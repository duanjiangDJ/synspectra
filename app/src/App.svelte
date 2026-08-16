<script lang="ts">
  import { onMount } from "svelte";

  import ConfirmDialog from "./components/ConfirmDialog.svelte";
  import TabBar from "./components/TabBar.svelte";
  import Toasts from "./components/Toasts.svelte";
  import { activeTab } from "./lib/appState";
  import Config from "./pages/Config.svelte";
  import Resources from "./pages/Resources.svelte";
  import Results from "./pages/Results.svelte";
  import Run from "./pages/Run.svelte";
  import Workspace from "./pages/Workspace.svelte";
  import { startListening } from "./lib/taskEvents";

  const tabs = [
    { id: "workspace", labelKey: "nav.workspace" },
    { id: "config", labelKey: "nav.config" },
    { id: "run", labelKey: "nav.run" },
    { id: "resources", labelKey: "nav.resources" },
    { id: "results", labelKey: "nav.results" },
  ];

  function selectTab(id: string): void {
    activeTab.set(id);
  }

  onMount(() => {
    startListening();
  });
</script>

<div class="app-shell">
  <header class="titlebar">
    <TabBar {tabs} active={$activeTab} onSelect={selectTab} />
  </header>
  <main class="page">
    {#if $activeTab === "workspace"}
      <Workspace />
    {:else if $activeTab === "config"}
      <Config />
    {:else if $activeTab === "run"}
      <Run />
    {:else if $activeTab === "resources"}
      <Resources />
    {:else}
      <Results />
    {/if}
  </main>
  <Toasts />
  <ConfirmDialog />
</div>
