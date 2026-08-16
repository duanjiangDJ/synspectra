<script lang="ts">
  import { get } from "svelte/store";
  import { onDestroy, onMount } from "svelte";

  import { bootRevision } from "../bridge/bridge";
  import {
    backendPaths,
    categories,
    corpusImporting,
    corpusMutation,
    corpusScan,
    corpusScanning,
    resourceDir,
    resultDir,
    sourceDir,
  } from "../lib/appState";
  import {
    chooseDirectory,
    chooseZipFile,
    getBackendPaths,
    scanSourceTree,
    spawnBackend,
  } from "../lib/backend";
  import { t } from "../lib/i18n";
  import { startListening } from "../lib/taskEvents";
  import { addToast, askConfirm, askInput } from "../lib/ui";

  let conflict = $state("skip");
  let scanError = $state("");
  let lastImported: number | undefined;
  let lastMutation = 0;

  async function scan(): Promise<void> {
    const dir = $sourceDir;
    if (!dir) {
      categories.set([]);
      return;
    }
    try {
      categories.set(await scanSourceTree(dir));
      scanError = "";
    } catch (err) {
      scanError = String(err);
    }
  }

  function backend(): {
    python: string;
    script: string;
    env: Record<string, string>;
  } | null {
    const paths = get(backendPaths);
    if (!paths?.venv_python || !paths.corpus_import) return null;
    return {
      python: paths.venv_python,
      script: paths.corpus_import,
      env: { ...(paths.env ?? {}), PYTHONUTF8: "1" },
    };
  }

  async function runCorpus(args: string[]): Promise<boolean> {
    const target = backend();
    if (!target) {
      corpusScanning.set(false);
      corpusImporting.set(false);
      addToast("error", "Python runtime is not installed. Install it on the Resources page first.", 8000);
      return false;
    }
    try {
      await spawnBackend({
        program: target.python,
        args: [target.script, ...args],
        env: target.env,
      });
      return true;
    } catch (err) {
      corpusScanning.set(false);
      corpusImporting.set(false);
      addToast("error", "Corpus command failed: " + String(err), 8000);
      return false;
    }
  }

  async function pickZip(): Promise<void> {
    const file = await chooseZipFile();
    if (file) {
      corpusScanning.set(true);
      corpusScan.set(null);
      await runCorpus(["scan", file]);
    }
  }

  async function pickDirectory(): Promise<void> {
    const dir = await chooseDirectory();
    if (dir) {
      corpusScanning.set(true);
      corpusScan.set(null);
      await runCorpus(["scan", dir]);
    }
  }

  async function confirmImport(): Promise<void> {
    const scan = get(corpusScan);
    if (!scan?.groups.length || !$sourceDir) return;
    if (conflict === "overwrite") {
      const ok = await askConfirm({
        title: $t("workspace.overwriteTitle"),
        message: $t("workspace.overwriteMessage"),
      });
      if (!ok) return;
    }
    corpusImporting.set(true);
    await runCorpus([
      "import",
      scan.input,
      "--source-dir",
      $sourceDir,
      "--conflict",
      conflict,
    ]);
  }

  async function renameScanned(index: number): Promise<void> {
    const group = $corpusScan?.groups[index];
    if (!group) return;
    const name = await askInput({
      title: $t("common.rename"),
      message: $t("workspace.renameGroupHint"),
      input: { label: $t("workspace.group"), value: group.name },
    });
    if (name && name !== group.name) {
      corpusScan.update((scan) => {
        if (!scan) return scan;
        const groups = [...scan.groups];
        groups[index] = { ...groups[index], name };
        return { ...scan, groups };
      });
    }
  }

  async function deleteScanned(index: number): Promise<void> {
    const ok = await askConfirm({
      title: $t("common.delete"),
      message: $t("workspace.deleteGroupMessage"),
    });
    if (ok) {
      corpusScan.update((scan) => {
        if (!scan) return scan;
        return {
          ...scan,
          groups: scan.groups.filter((_, itemIndex) => itemIndex !== index),
        };
      });
    }
  }

  async function renameCategory(name: string): Promise<void> {
    const newName = await askInput({
      title: $t("common.rename"),
      message: $t("workspace.renameGroupHint"),
      input: { label: $t("workspace.group"), value: name },
    });
    if (newName && newName !== name) {
      await runCorpus([
        "rename-category",
        "--source-dir",
        $sourceDir,
        "--old",
        name,
        "--new",
        newName,
      ]);
    }
  }

  async function deleteCategory(name: string): Promise<void> {
    const ok = await askConfirm({
      title: $t("common.delete"),
      message: $t("workspace.deleteCategoryMessage", { name }),
    });
    if (ok) {
      await runCorpus([
        "delete-category",
        "--source-dir",
        $sourceDir,
        "--name",
        name,
      ]);
    }
  }

  $effect(() => {
    const imported = $corpusScan?.imported;
    if (imported !== undefined && imported !== lastImported) {
      lastImported = imported;
      scan();
    }
  });

  $effect(() => {
    const mutation = $corpusMutation;
    if (mutation !== 0 && mutation !== lastMutation) {
      lastMutation = mutation;
      scan();
    }
  });

  async function init(): Promise<void> {
    try {
      const paths = await getBackendPaths($resourceDir || undefined);
      backendPaths.set(paths);
      const base = paths.repo_root ?? paths.data_dir;
      if (base) {
        if (!$sourceDir) sourceDir.set(base + "/source");
        if (!$resultDir) resultDir.set(base + "/result");
      }
      await scan();
    } catch (err) {
      scanError = String(err);
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
</script>

<section class="page-section">
  <h2>{$t("workspace.title")}</h2>

  <div class="card">
    <h3 class="card-title">{$t("workspace.importTitle")}</h3>
    <p class="muted small">{$t("workspace.importDesc")}</p>
    <div class="button-row">
      <button type="button" class="button" onclick={pickZip}>
        {$t("workspace.importZip")}
      </button>
      <button type="button" class="button" onclick={pickDirectory}>
        {$t("workspace.importDir")}
      </button>
      <label class="inline-label">
        {$t("workspace.conflict")}
        <select bind:value={conflict}>
          <option value="skip">{$t("workspace.conflictSkip")}</option>
          <option value="overwrite">{$t("workspace.conflictOverwrite")}</option>
        </select>
      </label>
    </div>

    {#if $corpusScanning}
      <div class="loading-row">
        <span class="spinner" aria-hidden="true"></span>
        <span class="muted">{$t("workspace.recognizing")}</span>
      </div>
    {/if}

    {#if $corpusScan}
      <div class="import-result">
        {#if $corpusScan.groups.length === 0}
          <p class="muted small">{$t("workspace.noGroups")}</p>
        {:else}
          <table class="data-table">
            <thead>
              <tr>
                <th>{$t("workspace.group")}</th>
                <th>{$t("workspace.files")}</th>
                <th class="table-actions"></th>
              </tr>
            </thead>
            <tbody>
              {#each $corpusScan.groups as group, index (index)}
                <tr>
                  <td>{group.name}</td>
                  <td>{group.file_count}</td>
                  <td class="table-actions">
                    <button
                      type="button"
                      class="button small-button"
                      onclick={() => renameScanned(index)}
                    >
                      {$t("common.rename")}
                    </button>
                    <button
                      type="button"
                      class="button small-button danger"
                      onclick={() => deleteScanned(index)}
                    >
                      {$t("common.delete")}
                    </button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
          <div class="button-row">
            <button
              type="button"
              class="button primary"
              disabled={$corpusImporting || !$sourceDir}
              onclick={confirmImport}
            >
              {$t("workspace.importConfirm")}
            </button>
            {#if $corpusImporting}
              <span class="spinner" aria-hidden="true"></span>
              {#if $corpusScan.progress}
                <span class="muted small">
                  {$t("workspace.importProgress", {
                    done: String($corpusScan.progress.done),
                    total: String($corpusScan.progress.total),
                  })}
                </span>
              {/if}
            {:else if $corpusScan.imported !== undefined}
              <span class="muted small">
                {$t("workspace.imported")}: {$corpusScan.imported}，
                {$t("workspace.skipped")}: {$corpusScan.skipped}
              </span>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <div class="card">
    <h3 class="card-title">{$t("workspace.categories")}</h3>
    {#if $categories.length === 0}
      <p class="muted small">{$t("workspace.scanHint")}</p>
    {:else}
      <table class="data-table">
        <thead>
          <tr>
            <th>{$t("workspace.group")}</th>
            <th>{$t("workspace.files")}</th>
            <th class="table-actions"></th>
          </tr>
        </thead>
        <tbody>
          {#each $categories as category (category.name)}
            <tr>
              <td>{category.name}</td>
              <td>{category.file_count}</td>
              <td class="table-actions">
                <button
                  type="button"
                  class="button small-button"
                  onclick={() => renameCategory(category.name)}
                >
                  {$t("common.rename")}
                </button>
                <button
                  type="button"
                  class="button small-button danger"
                  onclick={() => deleteCategory(category.name)}
                >
                  {$t("common.delete")}
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    {#if scanError}
      <p class="small error-text">{$t("workspace.scanError")}: {scanError}</p>
    {/if}
  </div>
</section>
