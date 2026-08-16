# Bridge Protocol（前端 ↔ 桌面载体）

本协议是 Web 应用（`app/`）与桌面载体（`desktop/`）之间的唯一接口。桌面壳在
loopback 地址（127.0.0.1）上运行一个 HTTP 静态服务 + WebSocket carrier，并向页面
注入 `window.__SYNM_BOOT__`。浏览器开发模式连接同一 carrier 协议（由
`desktop --headless` 或开发模式下的 carrier 服务器提供）。UI 代码中不允许出现任何
平台分支；平台信息仅通过 boot 对象暴露。

## 1. Boot 对象

```ts
interface BootInfo {
  env: "desktop" | "web" | "test";   // 载体环境
  platform: "win32" | "darwin" | "linux";
  wsUrl: string;                     // ws://127.0.0.1:<port>/carrier
  token: string;                     // 每次启动随机，用于 WS 握手校验
  paths: BackendPaths;               // 预解析路径（见下）
}

interface BackendPaths {
  repo_root: string | null;
  default_data_dir: string;          // 打包后为 exe 同级目录；开发为 <repo>/.desktop-data
  data_dir: string;                  // 实际资源数据目录（可由用户在资源页覆盖）
  venv_python: string | null;        // 仓库 .venv 或受管 <data_dir>/venv
  uv: string | null;                 // 仓库 .venv 或打包内置 bin/uv
  run_metrics: string | null;
  resource_manager: string | null;
  manifest: string | null;
  env: Record<string, string>;       // STANZA_RESOURCES_DIR / JAVA_HOME / PATH / STANFORD_*_HOME
}
```

打包模式下 boot 由 loopback 服务器以带 nonce 的内联脚本注入 index.html；开发模式下
（Electron 窗口加载 Vite dev URL）由 main 进程在 did-finish-load 后通过
`executeJavaScript` 注入并派发 `CustomEvent("synm:boot")`，应用监听该事件重新初始化
bridge。浏览器调试时也可通过查询参数 `?ws=ws://127.0.0.1:<port>/carrier&token=...`
指定 carrier。

## 2. WebSocket carrier

- 端点：`/carrier`，握手必须携带 `?token=<boot.token>`，否则拒绝升级。
- 客户端 → 服务器（请求）：

```json
{ "id": 1, "method": "backend_paths", "params": { "dataDir": "..." }, "token": "<token>" }
```

- 服务器 → 客户端（响应或事件）：

```json
{ "id": 1, "ok": true, "result": { "..." } }
{ "id": 2, "ok": false, "error": { "code": "SPAWN_FAILED", "message": "..." } }
{ "type": "event", "stream": "backend://event", "line": "<JSON 事件行>" }
{ "type": "event", "stream": "backend://raw", "line": "<原始输出行>" }
{ "type": "event", "stream": "backend://stderr", "line": "<stderr 行>" }
```

## 3. RPC 方法

| 方法 | 参数 | 结果 | 说明 |
| --- | --- | --- | --- |
| `backend_paths` | `{ dataDir? }` | `BackendPaths` | 解析路径与子进程环境 |
| `scan_source_dir` | `{ sourceDir }` | `CategoryInfo[]` | 单层类别扫描（跳过 `*_results_dd`） |
| `scan_source_tree` | `{ sourceDir }` | `CategoryInfo[]` | 递归扫描（深度 ≤ 10，按相对路径命名分组） |
| `list_csv_files` | `{ resultDir }` | `string[]` | 列出结果目录 CSV |
| `read_csv_preview` | `{ path, maxRows? }` | `{ headers, rows }` | CSV 预览（上限 500 行） |
| `path_exists` | `{ path }` | `boolean` | |
| `set_always_on_top` | `{ enabled }` | `null` | |
| `open_in_file_manager` | `{ path }` | `null` | explorer / open -R / xdg-open |
| `choose_directory` | `{}` | `string \| null` | 原生目录选择 |
| `choose_zip_file` | `{}` | `string \| null` | 原生 zip 选择 |
| `spawn_backend` | `{ request: SpawnRequest }` | `number`（childId） | 启动后端脚本并转发输出 |
| `kill_backend` | `{ childId }` | `null` | 终止进程树（Windows taskkill /T /F；POSIX kill(-pid)） |
| `bootstrap_runtime` | `{ uvPath, requirements, pythonVersion, dataDir }` | `null` | 异步执行 uv 引导，进度经 resource 事件推送 |

`SpawnRequest = { program: string; args: string[]; env: Record<string, string> }`

## 4. 事件流（与 Python JSONL 的映射）

- Python 后端 `--log-format jsonl` 的 stdout 每一行原样转发为
  `backend://event`；同时转发一份到 `backend://raw`。
- stderr 行转发为 `backend://stderr` + `backend://raw`。
- 事件类型见 `docs/backend-contract.md`。
- 桌面壳自产事件：`resource`（id=python_runtime 的 uv 引导进度）、
  `error`（code=BOOTSTRAP_FAILED）。

## 5. 安全边界

- HTTP/WS 仅绑定 127.0.0.1；token 每次启动随机。
- 页面 `contextIsolation: true`、`sandbox: true`、`nodeIntegration: false`，无 preload、
  无 Electron IPC；唯一通信途径是 carrier。
- 打包模式对 index.html 返回带 nonce 的 CSP；
  `will-navigate` 阻止离开 loopback 源，外链委托 `shell.openExternal`。
