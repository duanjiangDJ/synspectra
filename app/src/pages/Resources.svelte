<script lang="ts">
  import { onMount } from "svelte";

  import { bootRevision } from "../bridge/bridge";
  import {
    backendPaths,
    bulkInstalling,
    resourceDir,
    resourceErrors,
    resourceProgress,
    resourceReady,
    resourceStatuses,
    resourceTasks,
    setResourceDir,
  } from "../lib/appState";
  import {
    chooseDirectory,
    chooseZipFile,
    getBackendPaths,
  } from "../lib/backend";
  import { t } from "../lib/i18n";
  import {
    bootstrapPythonRuntime,
    importOfflineBundle,
    installAllResources,
    installResource,
    refreshResourceReadiness,
    uninstallPythonRuntime,
    uninstallResource,
    verifyResources,
  } from "../lib/resources";
  import { startListening } from "../lib/taskEvents";
  import { addToast } from "../lib/ui";

  interface ResourceItem {
    id: string;
    key: string;
    installable: boolean;
  }

  interface ResourceGroup {
    groupKey: string;
    items: ResourceItem[];
  }

  const groups: ResourceGroup[] = [
    {
      groupKey: "resources.group.runtime",
      items: [{ id: "python", key: "resources.item.python", installable: true }],
    },
    {
      groupKey: "resources.group.models",
      items: [
        { id: "udpipe_model", key: "resources.item.udpipe", installable: true },
        { id: "stanza_model", key: "resources.item.stanza", installable: true },
      ],
    },
    {
      groupKey: "resources.group.neosca",
      items: [
        { id: "jre", key: "resources.item.jre", installable: true },
        { id: "stanford_parser", key: "resources.item.parser", installable: true },
        { id: "stanford_tregex", key: "resources.item.tregex", installable: true },
      ],
    },
  ];

  let loaded = $state(false);
  let detecting = $state(false);

  function formatProgress(value: { done: number; total: number }): string {
    const mb = (bytes: number): string => (bytes / (1024 * 1024)).toFixed(2);
    const percent =
      value.total > 0 ? ((value.done / value.total) * 100).toFixed(2) : "0.00";
    return mb(value.done) + " MB / " + mb(value.total) + " MB (" + percent + "%)";
  }

  async function loadPaths(): Promise<void> {
    const dir = $resourceDir;
    backendPaths.set(await getBackendPaths(dir || undefined));
  }

  async function detect(): Promise<void> {
    detecting = true;
    await refreshResourceReadiness();
    detecting = false;
    loaded = true;
    addToast("success", "Detection finished", 3000);
  }

  async function init(): Promise<void> {
    await loadPaths();
    await detect();
  }

  onMount(() => {
    startListening();
    void init();
    const unsubscribe = bootRevision.subscribe((value) => {
      if (value > 0) void init();
    });
    return () => unsubscribe();
  });

  async function choosePath(): Promise<void> {
    const dir = await chooseDirectory();
    if (dir) {
      setResourceDir(dir);
      await loadPaths();
      await detect();
    }
  }

  async function resetPath(): Promise<void> {
    setResourceDir("");
    await loadPaths();
    await detect();
  }

  async function importOffline(): Promise<void> {
    const bundle = await chooseZipFile();
    if (bundle) {
      await importOfflineBundle(bundle);
      await detect();
    }
  }

  function statusFor(id: string): string {
    const live = $resourceStatuses[id];
    if (live && live !== "not_installed") return live;
    if (detecting) return $resourceReady[id] ? "ready" : "connecting";
    if ($bulkInstalling && !$resourceReady[id]) return "queued";
    return $resourceReady[id] ? "ready" : "not_installed";
  }

  function isBusy(status: string): boolean {
    return ["connecting", "downloading", "installing", "queued"].includes(status);
  }

  function anyTaskInFlight(): boolean {
    return Object.keys($resourceTasks).length > 0 || $bulkInstalling;
  }

  async function handleAction(item: ResourceItem): Promise<void> {
    const current = statusFor(item.id);
    if (isBusy(current)) return;
    if (current === "ready") {
      if (item.id === "python") {
        await uninstallPythonRuntime();
      } else {
        await uninstallResource(item.id);
      }
      resourceStatuses.update((items) => {
        const next = { ...items };
        delete next[item.id];
        return next;
      });
      resourceProgress.update((items) => {
        const next = { ...items };
        delete next[item.id];
        return next;
      });
      await detect();
      return;
    }
    if (item.id === "python") {
      await bootstrapPythonRuntime();
    } else {
      await installResource(item.id);
    }
  }
</script>

<section class="page-section">
  <h2>{$t("resources.title")}</h2>
  <p class="muted">{$t("resources.description")}</p>

  <div class="card">
    <h3 class="card-title">{$t("resources.customPath")}</h3>
    <div class="path-row">
      <code class="path-value">{$resourceDir || $backendPaths?.default_data_dir || "—"}</code>
      <button type="button" class="button secondary" onclick={choosePath}>
        {$t("resources.choosePath")}
      </button>
      <button type="button" class="button secondary" onclick={resetPath}>
        {$t("resources.resetPath")}
      </button>
    </div>
    <p class="muted small">{$t("resources.pathHint")}</p>
    <div class="button-row">
      <button
        type="button"
        class="button primary"
        disabled={!loaded || (!$backendPaths?.venv_python && !$backendPaths?.uv) || anyTaskInFlight()}
        onclick={() => {
          void installAllResources();
        }}
      >
        {$t("resources.installAll")}
      </button>
      <button
        type="button"
        class="button"
        disabled={!loaded || !$backendPaths?.venv_python || anyTaskInFlight()}
        onclick={() => {
          void verifyResources();
        }}
      >
        {$t("resources.verify")}
      </button>
      <button
        type="button"
        class="button"
        disabled={!loaded || !$backendPaths?.venv_python || anyTaskInFlight()}
        onclick={importOffline}
      >
        {$t("resources.offlineImport")}
      </button>
      <button type="button" class="button" disabled={!loaded} onclick={detect}>
        {detecting ? $t("resources.detecting") : $t("resources.detect")}
      </button>
    </div>
  </div>

  {#each groups as group (group.groupKey)}
    <div class="card">
      <h3 class="card-title">{$t(group.groupKey)}</h3>
      {#each group.items as item (item.id)}
        <div class="resource-row">
          <span>{$t(item.key)}</span>
          <span class="status-tag neutral">{$t("resources.status." + statusFor(item.id))}</span>
          {#if $resourceProgress[item.id]?.total > 0}
            <span class="small muted">{formatProgress($resourceProgress[item.id])}</span>
            <div class="progress-track small-progress">
              <div
                class="progress-fill"
                style:width="{Math.round(
                  ($resourceProgress[item.id].done /
                    $resourceProgress[item.id].total) *
                    100,
                )}%"
              ></div>
            </div>
          {/if}
          {#if $resourceErrors[item.id]}
            <p class="small error-text resource-error">{$resourceErrors[item.id]}</p>
          {/if}
          {#if item.installable}
            <button
              type="button"
              class="button small-button"
              class:danger={statusFor(item.id) === "ready"}
              disabled={isBusy(statusFor(item.id))}
              onclick={() => handleAction(item)}
            >
              {statusFor(item.id) === "ready"
                ? $t("resources.delete")
                : $t("resources.install")}
            </button>
          {/if}
        </div>
      {/each}
    </div>
  {/each}
</section>
