<script lang="ts">
  import { onMount } from "svelte";

  import { bootRevision } from "../bridge/bridge";
  import Modal from "../components/Modal.svelte";
  import {
    backendPaths,
    resourceDir,
    resultDir,
    resultFiles,
  } from "../lib/appState";
  import {
    getBackendPaths,
    listCsvFiles,
    openInFileManager,
    readCsvPreview,
  } from "../lib/backend";
  import { t } from "../lib/i18n";
  import { startListening } from "../lib/taskEvents";

  let preview = $state<{
    file: string;
    headers: string[];
    rows: string[][];
  } | null>(null);

  async function init(): Promise<void> {
    try {
      const paths = await getBackendPaths($resourceDir || undefined);
      backendPaths.set(paths);
      const base = paths.repo_root ?? paths.data_dir;
      if (base && !$resultDir) {
        resultDir.set(base + "/result");
      }
      if ($resultDir) {
        resultFiles.set(await listCsvFiles($resultDir));
      }
    } catch {
      // backend unavailable
    }
  }

  onMount(() => {
    startListening();
    void init();
    const unsubscribe = bootRevision.subscribe((value) => {
      if (value > 0) void init();
    });
    return () => unsubscribe();
  });

  async function openDir(): Promise<void> {
    if ($resultDir) await openInFileManager($resultDir);
  }

  async function previewFile(file: string): Promise<void> {
    if (!$resultDir) return;
    const data = await readCsvPreview($resultDir + "/" + file);
    preview = { file, headers: data.headers, rows: data.rows };
  }
</script>

<section class="page-section">
  <div class="results-header">
    <h2>{$t("results.title")}</h2>
    <button
      type="button"
      class="button secondary"
      disabled={!$resultDir}
      onclick={openDir}
    >
      {$t("results.openDir")}
    </button>
  </div>
  <p class="muted">{$t("results.description")}</p>

  <div class="card">
    {#if $resultFiles.length === 0}
      <p class="muted">{$t("results.empty")}</p>
    {:else}
      <table class="data-table">
        <thead>
          <tr>
            <th>{$t("results.file")}</th>
            <th class="table-actions"></th>
          </tr>
        </thead>
        <tbody>
          {#each $resultFiles as file (file)}
            <tr>
              <td><code>{file}</code></td>
              <td class="table-actions">
                <button
                  type="button"
                  class="button small-button"
                  onclick={() => previewFile(file)}
                >
                  {$t("results.preview")}
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  <Modal
    open={preview !== null}
    title={preview ? $t("results.preview") + ": " + preview.file : ""}
    onClose={() => (preview = null)}
    width="820px"
  >
    {#if preview}
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              {#each preview.headers as header (header)}
                <th>{header}</th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each preview.rows as row, index (index)}
              <tr>
                {#each row as cell, cellIndex (index + "-" + cellIndex)}
                  <td>{cell}</td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="muted small">{$t("results.previewLimit")}</p>
    {/if}
  </Modal>
</section>
