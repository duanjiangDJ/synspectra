<script lang="ts">
  import { onMount } from "svelte";

  import { bootRevision, bridgeKind } from "../bridge/bridge";
  import {
    backendPaths,
    lastTaskStatus,
    methods,
    navigate,
    progress,
    rawLogs,
    resourceReady,
    resultDir,
    sourceDir,
    taskRunning,
  } from "../lib/appState";
  import Console from "../components/Console.svelte";
  import { stageLabel } from "../lib/console";
  import { t } from "../lib/i18n";
  import { isMethodReady, refreshResourceReadiness } from "../lib/resources";
  import { startListening, startRun, stopRun } from "../lib/taskEvents";

  let readinessChecked = $state(false);

  const missingMethods = $derived(
    Object.entries($methods)
      .filter(([, enabled]) => enabled)
      .map(([id]) => id)
      .filter((id) => !isMethodReady(id, $resourceReady)),
  );
  const blockedByResources = $derived(
    $bridgeKind === "rpc" && readinessChecked && missingMethods.length > 0,
  );

  // Parallel chunk hint: the backend stage message announces "Parsing N
  // files with M workers" — surface the worker count as a live badge.
  const workersActive = $derived.by(() => {
    const message = $progress?.stageMessage ?? "";
    const match = message.match(/with (\d+) workers/);
    return match ? Number(match[1]) : 0;
  });
  const stageDetail = $derived(
    $progress?.stageMessage && $progress.stageMessage.length > 0
      ? $progress.stageMessage
      : "",
  );

  async function init(): Promise<void> {
    if (!$backendPaths) {
      const { getBackendPaths } = await import("../lib/backend");
      backendPaths.set(await getBackendPaths());
    }
    await refreshResourceReadiness();
    readinessChecked = true;
  }

  onMount(() => {
    startListening();
    void init();
    const unsubscribe = bootRevision.subscribe((value) => {
      if (value > 0) void init();
    });
    return () => unsubscribe();
  });

  async function copyLogs(): Promise<void> {
    // Copy the raw backend lines (useful for support/debugging).
    await navigator.clipboard.writeText($rawLogs.join("\n"));
  }

  function clearLogs(): void {
    rawLogs.set([]);
  }
</script>

<section class="page-section">
  <h2>{$t("run.title")}</h2>
  <p class="muted">{$t("run.description")}</p>

  <div class="card">
    <div class="run-actions">
      <button
        type="button"
        class="button primary"
        disabled={$taskRunning || blockedByResources || !$sourceDir || !$resultDir}
        onclick={startRun}
      >
        {$t("run.start")}
      </button>
      <button
        type="button"
        class="button danger"
        disabled={!$taskRunning}
        onclick={stopRun}
      >
        {$t("run.stop")}
      </button>
    </div>
    <p class="muted small">
      {#if blockedByResources}
        {$t("run.missingResources")}
        <button type="button" class="link-button" onclick={() => navigate("resources")}>
          {$t("config.goResources")}
        </button>
      {:else if !$sourceDir || !$resultDir}
        {$t("run.notConfigured")}
      {:else if $taskRunning}
        {$t("run.running")}
      {:else if $lastTaskStatus === "success"}
        {$t("run.lastSuccess")}
      {:else if $lastTaskStatus === "error"}
        {$t("run.lastFailed")}
      {:else if $lastTaskStatus === "cancelled"}
        {$t("run.lastCancelled")}
      {:else}
        {$t("run.ready")}
      {/if}
    </p>

    <div class="stat-grid">
      <div class="stat">
        <span class="stat-label">{$t("run.progress")}</span>
        <span class="stat-value">
          {$progress?.done ?? 0} / {$progress?.total ?? 0}
        </span>
      </div>
      <div class="stat">
        <span class="stat-label">{$t("run.currentFile")}</span>
        <span class="stat-value">{$progress?.file || "—"}</span>
      </div>
      <div class="stat">
        <span class="stat-label">{$t("run.stage")}</span>
        <span class="stat-value">{stageLabel($progress?.stage ?? "") || "—"}</span>
      </div>
      <div class="stat">
        <span class="stat-label">{$t("run.category")}</span>
        <span class="stat-value">{$progress?.category || "—"}</span>
      </div>
    </div>

    {#if $progress?.total}
      <div class="progress-track" aria-label={$t("run.progress")}>
        <div
          class="progress-fill"
          style:width="{Math.round((($progress?.done ?? 0) / $progress.total) * 100)}%"
        ></div>
      </div>
    {/if}

    {#if stageDetail}
      <div class="stage-detail-row">
        {#if workersActive > 0}
          <span class="parallel-badge">⚡ {$workersActive} workers</span>
        {/if}
        <span class="muted small stage-detail-text">{stageDetail}</span>
      </div>
    {/if}
  </div>

  <div class="card">
    <h3 class="card-title">{$t("console.title")}</h3>
    <Console lines={$rawLogs} />
    <div class="button-row">
      <button
        type="button"
        class="button secondary"
        onclick={copyLogs}
        disabled={$rawLogs.length === 0}
      >
        {$t("console.copy")}
      </button>
      <button
        type="button"
        class="button secondary"
        onclick={clearLogs}
        disabled={$rawLogs.length === 0}
      >
        {$t("console.clear")}
      </button>
    </div>
  </div>
</section>
