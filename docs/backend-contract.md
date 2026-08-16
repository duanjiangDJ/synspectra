# Backend Contract（Python 后端 JSONL 事件契约）

前端与桌面壳不解析后端语义，只转发/消费以下 JSONL 事件。三份脚本均以
`--log-format jsonl` 启动，每行一个 JSON 对象。

## 1. run_metrics.py（metric_modules/event_logger.py 定义）

- `task/start`：`{"type":"task","event":"start","task_id":"...","preset":null,"methods":["custom","leo","quansyn"]}`
- `task/end`：`{"type":"task","event":"end","task_id":"...","status":"success","output_files":["result/text.csv"]}`
- `stage`：`{"type":"stage","stage":"category|file|custom|leo|quansyn|neosca|stanza","message":"..."}`
- `progress`：`{"type":"progress","task_id":"...","category":"text","file":"text1.txt","stage":"write","done":1,"total":6}`
- `log`：`{"type":"log","level":"info|warning","message":"..."}`
- `error`：`{"type":"error","task_id":"...","code":"PIPELINE_FAILED|STANZA_PARSE_FAILED|QUANSYN_CALC_FAILED|NEOSCA_*|LEO_CALC_FAILED|SOURCE_NOT_FOUND","title":"...","detail":"...","suggestion":"..."}`

约定：
- 每个样本写盘后发送一条 `progress`（stage=write），前端进度条消费它。
- 任务成功/失败以 `task/end` 为准；`error` 事件可能先于 `task/end` 出现。
- 断点续传：已处理文件名保存在输出 CSV 的 `filename` 列，前端无需维护状态。

## 2. scripts/corpus_import.py

- 扫描结果：`{"type":"corpus","event":"scan","input":"...","groups":[{"path":"...","name":"...","file_count":N}]}`
- 导入进度：`{"type":"corpus","event":"progress","done":N,"total":N}`
- 导入完成：`{"type":"corpus","event":"done","imported":N,"skipped":N,"source_dir":"..."}`
- 重命名/删除：`{"type":"corpus","event":"renamed","old":"...","new":"..."}` /
  `{"type":"corpus","event":"deleted","name":"..."}`
- 失败：`{"type":"corpus","event":"error","detail":"..."}`（退出码 1）

CLI：`scan <input>`、`import <input> --source-dir X --conflict skip|overwrite`、
`rename-category --source-dir X --old A --new B`、`delete-category --source-dir X --name A`。
冲突策略只有 skip/overwrite 两种（无 rename）。

## 3. scripts/resource_manager.py

- `resource`：`{"type":"resource","id":"stanza_model|udpipe_model|jre|stanford_parser|stanford_tregex|python_runtime","status":"connecting|downloading|verifying|extracting|installing|ready|download_failed|install_failed|not_installed|outdated","bytes_done":N,"bytes_total":N,"detail":"..."}`
- `log`：安装过程中的信息/警告。
- `error`：`{"type":"error","code":"...","title":"...","detail":"...","suggestion":"..."}`

CLI：`install [resource|all]`、`verify [resource|all]`、`uninstall <resource>`、
`status`、`disk-usage`、`offline-import <bundle.zip>`；公共参数 `--data-dir`、
`--manifest`、`--log-format jsonl`。

## 4. 桌面壳自产事件（不属于 Python 后端）

- uv 引导（bootstrap_runtime）：`{"type":"resource","id":"python_runtime","status":"installing|ready","detail":"..."}`
- 引导失败：`{"type":"error","code":"BOOTSTRAP_FAILED","title":"...","detail":"...","suggestion":"..."}`
- uv 输出逐行转 `{"type":"log","level":"info|warning","message":"..."}`
