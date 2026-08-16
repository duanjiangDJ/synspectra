<script lang="ts">
  import { onMount } from "svelte";

  import { bridgeKind } from "../bridge/bridge";
  import Checkbox from "../components/Checkbox.svelte";
  import {
    alwaysOnTop,
    backendPaths,
    forceRerun,
    methods,
    navigate,
    resourceReady,
    resume,
    resultDir,
    sourceDir,
  } from "../lib/appState";
  import { chooseDirectory, getBackendPaths, setAlwaysOnTop } from "../lib/backend";
  import { locale, setLocale, t, type Locale } from "../lib/i18n";
  import { isMethodReady, refreshResourceReadiness } from "../lib/resources";
  import { setTheme, theme, type Theme } from "../lib/theme";

  const methodList = ["custom", "leo", "quansyn", "neosca"];

  const presets: Record<string, Record<string, boolean>> = {
    all: { custom: true, leo: true, quansyn: true, neosca: true },
    neosca: { custom: false, leo: false, quansyn: false, neosca: true },
    other: { custom: true, leo: true, quansyn: true, neosca: false },
  };

  const locales: { value: Locale; label: string }[] = [
    { value: "zh-CN", label: "中文" },
    { value: "en", label: "English" },
  ];

  const themes: { value: Theme; label: string }[] = [
    { value: "light", label: "" },
    { value: "dark", label: "" },
  ];

  let readinessChecked = $state(false);

  function applyPreset(key: string): void {
    methods.set({ ...presets[key] });
  }

  function toggleMethod(id: string, value: boolean): void {
    methods.update((items) => ({ ...items, [id]: value }));
  }

  function methodReady(id: string): boolean {
    if ($bridgeKind !== "rpc" || !readinessChecked) return true;
    return isMethodReady(id, $resourceReady);
  }

  function anyMissingReady(): boolean {
    if ($bridgeKind !== "rpc" || !readinessChecked) return false;
    return methodList.some(
      (id) => $methods[id] && !isMethodReady(id, $resourceReady),
    );
  }

  function selectRunOption(option: "resume" | "force"): void {
    if (option === "resume") {
      if ($resume) {
        resume.set(false);
      } else {
        resume.set(true);
        forceRerun.set(false);
      }
    } else if ($forceRerun) {
      forceRerun.set(false);
    } else {
      forceRerun.set(true);
      resume.set(false);
    }
  }

  async function toggleAlwaysOnTop(): Promise<void> {
    const next = !$alwaysOnTop;
    alwaysOnTop.set(next);
    await setAlwaysOnTop(next);
  }

  async function chooseResult(): Promise<void> {
    const dir = await chooseDirectory();
    if (dir) resultDir.set(dir);
  }

  async function init(): Promise<void> {
    if (!$backendPaths) {
      backendPaths.set(await getBackendPaths());
    }
    await refreshResourceReadiness();
    readinessChecked = true;
  }

  onMount(() => {
    void init();
  });
</script>

<section class="page-section">
  <h2>{$t("config.title")}</h2>
  <p class="muted">{$t("config.description")}</p>

  <div class="config-row">
    <div class="card">
      <h3 class="card-title">{$t("config.preset")}</h3>
      <div class="segmented-vertical" role="group" aria-label={$t("config.preset")}>
        <button
          type="button"
          class="segment"
          class:active={JSON.stringify($methods) === JSON.stringify(presets.all)}
          onclick={() => applyPreset("all")}
        >
          {$t("config.presetAll")}
        </button>
        <button
          type="button"
          class="segment"
          class:active={JSON.stringify($methods) === JSON.stringify(presets.neosca)}
          onclick={() => applyPreset("neosca")}
        >
          {$t("config.presetNeosca")}
        </button>
        <button
          type="button"
          class="segment"
          class:active={JSON.stringify($methods) === JSON.stringify(presets.other)}
          onclick={() => applyPreset("other")}
        >
          {$t("config.presetOther")}
        </button>
      </div>
    </div>

    <div class="card">
      <h3 class="card-title">{$t("config.methods")}</h3>
      <div class="method-grid-2x2">
        {#each methodList as method (method)}
          <Checkbox
            checked={$methods[method]}
            label={method}
            disabled={!methodReady(method)}
            onChange={(value) => toggleMethod(method, value)}
          />
        {/each}
      </div>
      {#if $bridgeKind === "rpc" && !readinessChecked}
        <p class="muted small">{$t("config.detectingResources")}</p>
      {:else if anyMissingReady()}
        <p class="small warning-text">
          {$t("config.missingResourceHint")}
          <button type="button" class="link-button" onclick={() => navigate("resources")}>
            {$t("config.goResources")}
          </button>
        </p>
      {:else}
        <p class="muted small">{$t("config.notReadyHint")}</p>
      {/if}
    </div>
  </div>

  <div class="config-row">
    <div class="card">
      <h3 class="card-title">{$t("config.runOptions")}</h3>
      <div class="segmented" role="group" aria-label={$t("config.runOptions")}>
        <button
          type="button"
          class="segment"
          class:active={$resume}
          onclick={() => selectRunOption("resume")}
        >
          {$t("config.resume")}
        </button>
        <button
          type="button"
          class="segment"
          class:active={$forceRerun}
          onclick={() => selectRunOption("force")}
        >
          {$t("config.forceRerun")}
        </button>
      </div>

    </div>

    <div class="card">
      <h3 class="card-title">{$t("config.interface")}</h3>
      <div class="path-row">
        <span class="path-label">{$t("common.language")}</span>
        <div class="segmented" role="group" aria-label={$t("common.language")}>
          {#each locales as item (item.value)}
            <button
              type="button"
              class="segment"
              class:active={$locale === item.value}
              onclick={() => setLocale(item.value)}
            >
              {item.label}
            </button>
          {/each}
        </div>
      </div>
      <div class="path-row">
        <span class="path-label">{$t("common.theme")}</span>
        <div class="segmented" role="group" aria-label={$t("common.theme")}>
          {#each themes as item (item.value)}
            <button
              type="button"
              class="segment"
              class:active={$theme === item.value}
              onclick={() => setTheme(item.value)}
            >
              {item.value === "light" ? $t("common.light") : $t("common.dark")}
            </button>
          {/each}
        </div>
      </div>
      <Checkbox
        checked={$alwaysOnTop}
        label={$t("config.keepOnTopOption")}
        onChange={toggleAlwaysOnTop}
      />
    </div>
  </div>

  <div class="card">
    <div class="path-row">
      <span class="path-label">{$t("workspace.sourceDir")}</span>
      <code class="path-value">{$sourceDir || "—"}</code>
      <span class="muted small">{$t("config.sourceHint")}</span>
    </div>
    <div class="path-row">
      <span class="path-label">{$t("workspace.resultDir")}</span>
      <code class="path-value">{$resultDir || "—"}</code>
      <button type="button" class="button secondary" onclick={chooseResult}>
        {$t("workspace.chooseDir")}
      </button>
    </div>
  </div>
</section>
