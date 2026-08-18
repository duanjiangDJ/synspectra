// E2E script executed inside the real app page by the desktop shell (--e2e).
// Drives the actual UI and the actual carrier; returns a result object.
export const E2E_SCRIPT = `
(() => {
  try {
  const report = { steps: [] };
  const step = (name, ok, detail) => report.steps.push({ name, ok, detail });

  const boot = window.__SYNM_BOOT__;
  if (!boot || !boot.paths) return Promise.resolve({ ok: false, reason: "boot missing", steps: report.steps });
  const paths = boot.paths;

  const openCarrier = () => new Promise((resolve, reject) => {
    const ws = new WebSocket(boot.wsUrl + "?token=" + encodeURIComponent(boot.token));
    ws.onopen = () => resolve(ws);
    ws.onerror = () => reject(new Error("carrier unreachable"));
  });

  let seq = 0;
  const rpc = (ws, method, params) => new Promise((resolve, reject) => {
    const id = ++seq;
    const onMessage = (event) => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === "event") return;
      if (message.id !== id) return;
      ws.removeEventListener("message", onMessage);
      if (message.ok) resolve(message.result); else reject(new Error(message.error ? message.error.message : "rpc failed"));
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id, method, params, token: boot.token }));
  });

  const waitFor = (predicate, timeoutMs) => new Promise((resolve) => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (predicate()) { clearInterval(timer); resolve(true); }
      else if (Date.now() - started > timeoutMs) { clearInterval(timer); resolve(false); }
    }, 120);
  });

  const tabs = [
    { id: "workspace", heading: "工作区", headingEn: "Workspace" },
    { id: "config", heading: "配置", headingEn: "Config" },
    { id: "run", heading: "运行", headingEn: "Run" },
    { id: "resources", heading: "资源管理器", headingEn: "Resource Manager" },
    { id: "results", heading: "结果", headingEn: "Results" },
    { id: "about", heading: "关于", headingEn: "About" },
  ];

  const clickTab = (index) => {
    const buttons = document.querySelectorAll(".tabbar .tab");
    if (!buttons[index]) return false;
    buttons[index].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    return true;
  };

  return (async () => {
    const ws = await openCarrier();
    try {
      // 1. paths
      const p = await rpc(ws, "backend_paths", {});
      step("backend_paths", !!p.run_metrics && !!p.venv_python, p.run_metrics);

      // 1b. window theme RPC (caption-button overlay colors)
      await rpc(ws, "set_theme", { theme: "dark" });
      step("set_theme", true);

      // 2. workspace scan
      const sourceBase = paths.repo_root || paths.data_dir;
      const groups = await rpc(ws, "scan_source_tree", { sourceDir: sourceBase + "/source" });
      step("scan_source_tree", Array.isArray(groups) && groups.length > 0, "groups=" + groups.length);

      // 3. results
      const csvs = await rpc(ws, "list_csv_files", { resultDir: sourceBase + "/result" });
      step("list_csv_files", Array.isArray(csvs) && csvs.length > 0, "csvs=" + csvs.length);
      if (csvs.length > 0) {
        const preview = await rpc(ws, "read_csv_preview", { path: sourceBase + "/result/" + csvs[0], maxRows: 5 });
        step("read_csv_preview", Array.isArray(preview.headers) && preview.headers.length > 0, "headers=" + preview.headers.length);
      }

      // 4. UI tabs render
      await waitFor(() => document.querySelectorAll(".tabbar .tab").length === 6, 8000);
      step("tabbar renders", document.querySelectorAll(".tabbar .tab").length === 6);
      for (let i = 0; i < tabs.length; i++) {
        if (!clickTab(i)) break;
        const ok = await waitFor(() => {
          const heading = document.querySelector(".page-section h2");
          if (!heading) return false;
          const text = heading.textContent.trim();
          return text === tabs[i].heading || text === tabs[i].headingEn;
        }, 5000);
        step("tab " + tabs[i].id, ok, ok ? "" : "heading mismatch: " + (document.querySelector(".page-section h2")?.textContent?.trim() ?? "NO_H2"));
      }

      // 5. spawn backend and receive event stream (listen before spawn to
      // avoid racing the child output)
      const sawTaskEndPromise = new Promise((resolve) => {
        let settled = false;
        let timer = null;
        const finish = (value) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          ws.removeEventListener("message", onMessage);
          resolve(value);
        };
        const onMessage = (event) => {
          let message;
          try { message = JSON.parse(event.data); } catch { return; }
          if (message.type === "event" && message.stream === "backend://event") {
            let payload;
            try { payload = JSON.parse(message.line); } catch { return; }
            // Structural check: the forwarded line must be the raw backend
            // JSON event (no double-encoded envelope).
            if (payload.type === "task" && payload.event === "end" && payload.task_id === "e2e") {
              finish(true);
            }
          }
        };
        ws.addEventListener("message", onMessage);
        timer = setTimeout(() => finish(false), 15000);
      });
      const childId = await rpc(ws, "spawn_backend", {
        request: {
          program: p.venv_python,
          args: ["-c", 'import json,sys;print(json.dumps({"type":"task","event":"end","task_id":"e2e","status":"success"}));print("E2E_MARKER_7f3a")'],
          env: { PYTHONUTF8: "1" },
        },
      });
      const sawTaskEnd = await sawTaskEndPromise;
      step("spawn+event stream", sawTaskEnd, "childId=" + childId);

      // 5b. the shell must also report the child exit event
      const sawChildExit = await new Promise((resolve) => {
        let settled = false;
        let timer = null;
        const finish = (value) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          ws.removeEventListener("message", onMessage);
          resolve(value);
        };
        const onMessage = (event) => {
          let message;
          try { message = JSON.parse(event.data); } catch { return; }
          if (message.type === "event" && message.stream === "backend://event") {
            let payload;
            try { payload = JSON.parse(message.line); } catch { return; }
            if (payload.type === "child" && payload.event === "exit" && Number(payload.child_id) === childId) {
              finish(true);
            }
          }
        };
        ws.addEventListener("message", onMessage);
        timer = setTimeout(() => finish(false), 15000);
      });
      step("child exit event", sawChildExit, "childId=" + childId);

      // 5c. the Run console must render structured lines, not raw JSON
      {
        const tabButtons = document.querySelectorAll(".tabbar .tab");
        tabButtons[2].dispatchEvent(new MouseEvent("click", { bubbles: true }));
        const rendered = await waitFor(() => {
          const lines = document.querySelectorAll(".console-box .console-line");
          return lines.length > 0;
        }, 8000);
        let noRawJson = true;
        let colored = false;
        let noDuplicates = true;
        if (rendered) {
          const texts = [...document.querySelectorAll(".console-box .console-text")].map(
            (node) => node.textContent ?? "",
          );
          noRawJson = texts.every((text) => !text.includes('"type"'));
          colored = document.querySelectorAll(".console-box .console-success, .console-box .console-info, .console-box .console-error").length > 0;
          // The unique marker line must arrive exactly once (no double
          // forwarding from duplicate carrier connections).
          const markerCount = texts.filter((text) => text.includes("E2E_MARKER_7f3a")).length;
          noDuplicates = markerCount === 1;
        }
        step("console structured rendering", rendered && noRawJson && colored, "noRawJson=" + noRawJson + " colored=" + colored);
        step("no duplicate log lines", rendered && noDuplicates, noDuplicates ? "marker x1" : "marker duplicated");
      }

      // 6. kill a long-running backend
      const longChild = await rpc(ws, "spawn_backend", {
        request: {
          program: p.venv_python,
          args: ["-c", "import time;time.sleep(120)"],
          env: {},
        },
      });
      await rpc(ws, "kill_backend", { childId: longChild });
      step("kill_backend", true, "killed=" + longChild);
    } catch (err) {
      step("fatal", false, String(err));
    } finally {
      ws.close();
    }
    const ok = report.steps.length > 0 && report.steps.every((s) => s.ok !== false);
    return { ok, steps: report.steps };
  })();
  } catch (err) {
    return Promise.resolve({ ok: false, reason: String((err && err.stack) || err), steps: [] });
  }
})()
`;
