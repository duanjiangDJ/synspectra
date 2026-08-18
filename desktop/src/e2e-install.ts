// Full first-run install flow test (--e2e-install): points the app at a
// fresh data dir, clicks "Install all" in the real UI, and waits until
// every resource row reports ready. Exercises bootstrap -> chaining ->
// resource_manager install-all end to end.
export function installScript(dataDir: string): string {
  return `
(() => {
  const report = { steps: [] };
  const DATA_DIR_VALUE = REPLACE_DATA_DIR_VALUE;
  const step = (name, ok, detail) => report.steps.push({ name, ok, detail });

  const waitFor = (predicate, timeoutMs) => new Promise((resolve) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (predicate()) { clearInterval(timer); resolve(true); }
      else if (Date.now() - started > timeoutMs) { clearInterval(timer); resolve(false); }
    }, 800);
  });

  const headingText = () => {
    const heading = document.querySelector(".page-section h2");
    return heading ? heading.textContent.trim() : "";
  };

  return (async () => {
    try {
      if (!window.__SYNM_BOOT__) return { ok: false, reason: "boot missing", steps: report.steps };

      // First pass: point the resource dir at the fresh data dir and reload.
      // localStorage persists across the reload (window properties do not).
      if (localStorage.getItem("__e2e_install_ready__") !== "1") {
        localStorage.setItem("__e2e_install_ready__", "1");
        localStorage.setItem("syntactic-metrics-resource-dir", DATA_DIR_VALUE);
        window.location.reload();
        return { ok: true, reloading: true, steps: report.steps };
      }

      // Open the Resources tab.
      await waitFor(() => document.querySelectorAll(".tabbar .tab").length === 6, 15000);
      const tabButtons = document.querySelectorAll(".tabbar .tab");
      tabButtons[3].dispatchEvent(new MouseEvent("click", { bubbles: true }));
      const onResources = await waitFor(
        () => headingText() === "资源管理器" || headingText() === "Resource Manager",
        8000,
      );
      step("open resources tab", onResources);

      // Wait until the page finished detecting and buttons are enabled.
      const findInstallAll = () => {
        const buttons = [...document.querySelectorAll("button")];
        return buttons.find((b) => {
          const text = b.textContent.trim();
          return text === "一键安装全部" || text === "Install all";
        }) || null;
      };
      const enabled = await waitFor(() => {
        const btn = findInstallAll();
        return !!btn && !btn.disabled;
      }, 30000);
      step("install-all enabled", enabled);

      // Click it.
      const clicked = await (() => {
        const btn = findInstallAll();
        if (!btn) return false;
        btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        return true;
      })();
      step("install-all clicked", clicked);

      // Poll all resource rows until every status tag reads ready.
      const readyTexts = ["已安装", "Installed"];
      const allReady = () => {
        const tags = [...document.querySelectorAll(".resource-row .status-tag")];
        return tags.length >= 6 && tags.every((tag) => readyTexts.includes(tag.textContent.trim()));
      };
      const wasFullyReady = allReady();
      const sawProgress = await waitFor(() => {
        const tags = [...document.querySelectorAll(".resource-row .status-tag")];
        return tags.some((tag) => {
          const text = tag.textContent.trim();
          return ["等待中", "Queued", "下载中", "Downloading", "安装中", "Installing"].includes(text);
        });
      }, 60000);
      // Progress states only exist when something still needs installing.
      step("progress states observed", sawProgress || wasFullyReady);
      const ready = await waitFor(allReady, 35 * 60 * 1000);
      step("all resources ready", ready, ready ? "" : "some rows never became ready");

      const ok = report.steps.every((s) => s.ok !== false);
      return { ok, steps: report.steps };
    } catch (err) {
      return { ok: false, reason: String((err && err.stack) || err), steps: report.steps };
    }
  })();
})()
`
    .replace("REPLACE_DATA_DIR_VALUE", JSON.stringify(dataDir));
}
