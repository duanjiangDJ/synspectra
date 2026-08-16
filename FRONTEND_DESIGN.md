# 前端正式设计文档（Electron carrier 架构）

## 1. 设计目标

本设计文档面向当前研究型批处理工具包的桌面前端实现。前端在不改变指标计算逻辑的前提下，为 `run_metrics.py` 与 `metric_modules/` 提供独立窗口、资源安装、图形化配置、运行控制、日志查看和结果预览能力。

设计目标：

- **同一运行（write once, run everywhere）**：同一份 UI 代码在纯浏览器（开发调试）、开发模式与打包桌面应用中行为一致；UI 内不允许出现任何平台分支。
- 跨平台：Windows 10（1809+）/ Windows 11、macOS、Linux。
- 轻量安装包：只含 Web 构建、Electron 壳、`uv`、后端脚本与资源清单；大体积资源按需下载。
- 开箱即用：首次启动通过页面内资源管理器完成 Python 运行时、依赖、模型与外部工具安装。
- 研究工具导向：界面清晰、直接、可复现。
- 保持管线可信度：前端只负责编排和展示，不重写指标算法；Python 回归（`mismatches []`）是硬验收。

## 2. 总体方案

参考 DeepSeek Harness Desktop 的 loopback carrier 模式：**Web 应用是第一公民，桌面壳只是一个带原生能力注入点的载体**。

| 层次 | 技术 | 说明 |
| --- | --- | --- |
| UI | Svelte 5 + TypeScript + Vite（`app/`） | 唯一 UI 代码库，零 Electron/Tauri 依赖 |
| 桌面壳 | Electron 43 + electron-builder（`desktop/`） | 只提供载体：loopback 服务、进程监督、原生对话框、打包 |
| 通信 | `window.__SYNM_BOOT__` 注入 + WebSocket carrier | 无 preload、无 IPC；renderer 沙箱化 |
| 样式 | CSS 设计令牌 + 自建组件 | 不引入重型组件库 |
| 运行时引导 | `uv`（内置） | 下载受管 CPython 3.11、建 venv、按 `requirements.lock` 安装 |
| Python 后端 | `run_metrics.py` / `scripts/resource_manager.py` / `scripts/corpus_import.py` | 保持原样，JSONL 事件被透明转发 |

明确不采用：PyInstaller/Nuitka 全量冻结（无法在线增装依赖）；Tauri IPC（新增能力必须写 Rust，平台分支扩散）。

### 2.1 Boot 注入与 carrier

- 打包模式：loopback HTTP 服务器（仅绑定 127.0.0.1）托管 `app/dist`，对 index.html 注入带 nonce 的内联脚本 `window.__SYNM_BOOT__ = {...}`，并返回带 nonce 的 CSP。
- 开发模式：Electron 窗口加载 Vite dev URL；main 进程在 did-finish-load 后 `executeJavaScript` 注入 boot 并派发 `CustomEvent("synm:boot")`，应用监听该事件重建 bridge（支持 HMR）。
- 浏览器模式：`desktop --headless` 只起 carrier 不建窗口；浏览器打开 `http://localhost:5173/?ws=ws://127.0.0.1:<port>/carrier&token=<token>`。
- 无宿主时 UI 自动降级为 mock bridge，便于纯前端演示与测试。

Boot 对象（契约见 `docs/bridge-protocol.md`）：`env`、`platform`、`wsUrl`、`token`（每次启动随机）、`paths`（含 `data_dir`、`venv_python`、`uv`、后端脚本路径与环境变量）。

### 2.2 应用内分层（`app/src/`）

| 模块 | 职责 |
| --- | --- |
| `bridge/contracts.ts` | RPC 方法与事件类型的唯一契约（前后端共享语义） |
| `bridge/carrier.ts` | WebSocket 客户端：请求/响应关联、事件订阅、断连错误 |
| `bridge/boot.ts` | 读取/解析 boot 目标（desktop / browser / mock） |
| `bridge/bridge.ts` | 桥生命周期：boot → carrier → RpcBridge/MockBridge；全局事件总线（桥切换时订阅不丢失） |
| `lib/backend.ts` | UI 侧唯一后端 API（与旧 Tauri 版同签名，页面零改动移植） |
| `lib/appState.ts` | 全局状态（路径、方法、任务、资源、语料、导航） |
| `lib/taskEvents.ts` | 事件分发、startRun 前置校验、stopRun |
| `lib/resources.ts` | 资源动作 + `refreshResourceReadiness`（配置页方法门控与资源页共用） |
| `lib/i18n.ts` / `lib/theme.ts` / `lib/ui.ts` | 双语、明暗主题、toast/确认对话框 |

### 2.3 桌面壳分层（`desktop/src/`）

| 模块 | 职责 |
| --- | --- |
| `main.ts` | 单实例、窗口、导航守卫（外链转系统浏览器）、dev 注入、`--smoke`/`--e2e`/`--headless` |
| `server.ts` | 静态服务（路径穿越防护 + MIME + CSP + boot 注入）+ WebSocket carrier（token 校验、RPC 分发、事件广播） |
| `supervisor.ts` | spawn/kill 后端进程；stdout→`backend://event`+raw，stderr→`backend://stderr`+raw；Windows taskkill /T /F，POSIX 进程组 kill |
| `bootstrap.ts` | uv 三步引导（python install → venv → pip install --require-hashes），进度经 resource 事件 |
| `methods.ts` | 13 个 RPC 处理器（路径/扫描/CSV 预览/对话框/置顶/文件管理器/spawn/kill/bootstrap） |
| `paths.ts` | 仓库根发现、数据目录策略（打包=exe 同级，开发=repo/.desktop-data）、环境变量组装 |
| `e2e.ts` | 页面世界内的端到端脚本（页面渲染、扫描、CSV、进程事件流、杀进程） |

### 2.4 安全边界

- HTTP/WS 只绑定 127.0.0.1；WS 升级校验每启动随机 token。
- `contextIsolation: true`、`sandbox: true`、`nodeIntegration: false`，无 preload、无 Electron IPC——renderer 只有浏览器能力 + carrier。
- 打包模式 CSP：`script-src 'self' 'nonce-...'`、`connect-src 'self' ws://127.0.0.1:*` 等；静态服务拒绝路径穿越。
- `will-navigate` 只允许 loopback 源；外链一律 `shell.openExternal`。
- 资源下载仍由 `scripts/resource_manager.py` 负责（HTTPS + SHA-256 + 安全解压），壳不重复实现。

## 3. 运行控制与事件流

- `startRun` 前置校验：路径齐备、至少一个方法启用、按方法查资源存在（Stanza/UDPipe/Java/Stanford）。
- 命令：`<venv-python> run_metrics.py --source-dir … --result-dir … --methods … --log-format jsonl [--leo-model-folder <data_dir>/models] [--no-resume]`。
- 进度条消费 `progress` 事件；控制台保留最近 400 行 raw 输出；`stopRun` 杀进程树，断点续传由 CSV 保证。
- 任务结束（task/end）自动刷新结果页列表。

## 4. 资源管理器

- 六项资源：python（受管运行时）、udpipe_model、stanza_model、jre、stanford_parser、stanford_tregex。
- 状态：`refreshResourceReadiness()` 检测就绪并写入 `resourceReady`；安装过程状态由 `resource` 事件实时驱动。
- 动作：单项安装/卸载、一键全部、校验（verify）、离线导入（zip）、自定义下载路径（持久化 localStorage）。
- **方法门控**：配置页按 `METHOD_RESOURCE_DEPS` 禁用资源未就绪的方法，并可跳转资源页。

## 5. 打包与发布

- `desktop/scripts/prepack.mjs`：暂存后端（run_metrics/metric_modules/corpus_import/resource_manager/清单/锁文件）、`app/dist`、`uv` 到 `desktop/resources/`。
- electron-builder：Windows NSIS、macOS dmg、Linux deb+AppImage；extraResources 将后端、Web 构建、uv 放在 asar 之外（Python 需要真实文件系统路径）。
- 三平台构建由 `.github/workflows/build.yml` 矩阵执行；Windows 侧本机验证（smoke/E2E/打包冒烟），macOS/Linux 依赖 CI。

## 6. 验收清单

- [x] `npm run check --workspace app` 与 `npm run typecheck --workspace desktop` 通过。
- [x] `npm run smoke`：boot 注入 + carrier RPC 往返 + UI 渲染。
- [x] `npm run e2e`：路径解析、目录扫描、CSV 预览、五个页面渲染、进程事件流、杀进程。
- [x] 集成测试（`desktop/scripts/integration-test.mjs`）：uv 引导受管运行时 → 受管 venv 跑 `--preset other` → task/end。
- [x] Python 回归：`--preset other` 输出与 `result/text.csv` 一致（`mismatches []`）。
- [x] Windows 打包（`dist:dir`）产物可运行并通过打包版 smoke。
- [ ] macOS/Linux 实机验证（CI 矩阵）。
