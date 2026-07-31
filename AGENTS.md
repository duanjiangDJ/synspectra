# 项目 Agent 工作规范

## 适用范围

本文件适用于整个仓库。执行任何代码、文档、配置或版本管理任务时，应同时参考 `README_CN.md`、`README.md`、`metrics_config.json` 与本文件。

如本文件与用户在当前对话中的明确要求冲突，以用户要求为准；如与旧文档冲突，以当前代码结构和本文件为准。

## 项目用途

本项目是一个用于英语文本语料的多维句法复杂度批处理工具。它按 `source/<类别>/` 组织输入文本，为每个 `.txt` 样本计算句法复杂度指标，并将每个类别的结果写入 `result/<类别>.csv`。

项目服务于定量语言学、二语写作研究、心理健康文本分析等需要批量比较句法特征的研究场景。当前整合的计算来源包括：

- 自定义依存距离指标：MDD、NDD、MHDD、AlphaDepLength。
- LeoDDcalculator 公式的 Python/UDPipe 复刻：`MDD_Leo`、`NDD_Leo`。
- QuanSyn `depval` 指标：依存距离、层级距离、配价、树宽、树高等。
- NeoSCA/L2SCA 指标：MLS、MLT、MLC、C/S、VP/T、T/S、复杂名词和结构频次等。

本项目的核心目标不是提供交互式应用，而是提供一个可配置、可断点续传、可复现实验结果的命令行计算流程。修改代码时应优先保证历史结果可对比、输出列稳定、配置开关清晰，并避免把某次实验的临时路径或生成数据固化进业务代码。

## 项目结构约定

- 根目录只保留一个 Python 入口脚本：`run_metrics.py`。
- 默认配置入口为 `metrics_config.json`，用于控制输入输出路径、断点续传、输出列和计算方法开关。
- 计算实现必须放在 `metric_modules/` 中：
  - `custom_metrics.py`：基于 Stanza CoNLL-U 的自定义 MDD、NDD、MHDD、AlphaDepLength。
  - `leo_dd.py`：LeoDDcalculator 的 Python/UDPipe 复刻实现。
  - `quansyn_metrics.py`：QuanSyn `depval` 集成。
  - `neosca_metrics.py`：NeoSCA 子进程集成。
  - `pipeline.py`：类别遍历、断点续传、CSV 写入和调度。
  - `config.py` 与 `fields.py`：默认配置、预设、方法开关和输出列。
  - `stanza_conllu.py` 与 `text_utils.py`：文本清洗与 CoNLL-U 转换等基础工具。
- 不要重新引入根目录跳转脚本，例如 `calculate_all_metrics.py`、`calculate_other_metrics.py`、`calculate_neosca.py` 或类似兼容包装。
- `result/`、`*_results_dd/`、`.venv/`、压缩包、`treebanks/`、`combine_index/`、`index/`、`__pycache__/` 均视为本地生成物、外部资源或环境文件，除非用户明确要求，否则不要纳入版本管理或修改其内容。

## 配置与运行流程

- 优先通过 `metrics_config.json` 表达默认行为，通过 `run_metrics.py` 参数表达一次性运行需求。
- 有效计算方法键固定为：`custom`、`leo`、`quansyn`、`neosca`。
- 常用运行方式：

```powershell
Set-Location 'e:\DMU\research\textAnalyse\index'
.\.venv\Scripts\python.exe run_metrics.py --config metrics_config.json
.\.venv\Scripts\python.exe run_metrics.py --preset other
.\.venv\Scripts\python.exe run_metrics.py --preset all
.\.venv\Scripts\python.exe run_metrics.py --preset neosca
.\.venv\Scripts\python.exe run_metrics.py --methods custom,leo,quansyn --no-resume
```

- 当修改、增加或重命名指标时，必须同步检查并更新：
  - 对应的 `metric_modules/*.py` 实现。
  - `metric_modules/fields.py` 中的字段列表。
  - `metrics_config.json` 中的默认开关和 `output_fields`。
  - `README_CN.md` 与 `README.md` 中的使用说明、输出列和依赖说明。
- 可复现实验配置中，`output_fields` 应与启用的方法保持一致。关闭某个方法时，不应保留该方法独有输出列，除非是为了兼容历史结果文件。
- LeoDD/UDPipe 模型目录由 `metrics_config.json` 中的 `leo.language_model_folder` 控制，默认模型路径为 `C:/english-ewt-ud-2.4-190531.udpipe`。不要在业务代码中新增未配置的绝对路径。

## 编码规范

- 保持 Python 3.8+ 兼容；如使用 `str | None`、`list[str]` 等现代类型写法，应保留 `from __future__ import annotations`。
- 保持当前朴素模块风格：小函数、显式字典、清晰的输入输出，不为简单流程增加不必要的类层级。
- 导入顺序遵循：标准库、第三方库、本项目模块。避免未使用导入。
- 不要使用含义不清的一字母变量名；短循环变量仅在含义显然且作用域很小时使用。
- 不要把新的计算逻辑塞进 `run_metrics.py`。根目录入口只负责解析参数、加载配置、调用管线。
- 新增计算方法时，应优先新建独立模块，并通过 `pipeline.py`、`config.py`、`fields.py` 接入。
- 外部工具调用应集中封装在对应模块中，例如 NeoSCA 子进程逻辑保留在 `neosca_metrics.py`。
- 读写结构化数据时优先使用 `csv`、`json` 等标准库或既有依赖，不使用脆弱的手写字符串拼接解析。

## 注释与日志规范

- 注释应少而准确。只在以下场景添加注释：
  - 非显然公式或指标定义。
  - 外部工具的特殊行为。
  - 生命周期或资源管理细节，例如 UDPipe `Model` 必须与 `Pipeline` 同时持有，避免底层指针失效。
- 不写解释显然代码的注释，例如“读取文件”“返回结果”。
- 用户文档优先使用中文 `README_CN.md`，英文 `README.md` 保持同步。
- CLI 参数、运行日志和异常信息可保持英文，但应简洁、可定位问题。

## 检查流程

根据改动范围选择最小但足够的检查。Windows PowerShell 中使用分号分隔命令，不使用 Bash 风格的 `&&`。

### 文档或配置改动

```powershell
Set-Location 'e:\DMU\research\textAnalyse\index'
git diff --check
.\.venv\Scripts\python.exe run_metrics.py --help
```

### Python 代码改动

```powershell
Set-Location 'e:\DMU\research\textAnalyse\index'
.\.venv\Scripts\python.exe -m compileall -q run_metrics.py metric_modules
.\.venv\Scripts\python.exe run_metrics.py --help
```

同时检查编辑器/Pylance 诊断。若有新增诊断，应优先修复与本次改动相关的问题。

### 影响 `custom`、`leo`、`quansyn`、配置或管线输出的改动

必须用现有 `source/text` 与 `result/text.csv` 做一致性回归，输出应满足 `mismatches []`。

```powershell
Set-Location 'e:\DMU\research\textAnalyse\index'
@'
import csv
import os
import shutil
import subprocess
import sys
import tempfile

base_dir = os.getcwd()
temp_dir = tempfile.mkdtemp()
try:
    subprocess.run(
        [sys.executable, 'run_metrics.py', '--preset', 'other', '--result-dir', temp_dir, '--no-resume'],
        check=True,
    )
    actual_path = os.path.join(temp_dir, 'text.csv')
    expected_path = os.path.join(base_dir, 'result', 'text.csv')

    with open(expected_path, encoding='utf-8', newline='') as f:
        expected_reader = csv.DictReader(f)
        expected_fields = expected_reader.fieldnames or []
        expected_rows = list(expected_reader)
    with open(actual_path, encoding='utf-8', newline='') as f:
        actual_reader = csv.DictReader(f)
        actual_fields = actual_reader.fieldnames or []
        actual_rows = list(actual_reader)

    mismatches = []
    if actual_fields != expected_fields:
        mismatches.append(('header', actual_fields, expected_fields))
    if len(actual_rows) != len(expected_rows):
        mismatches.append(('row_count', len(actual_rows), len(expected_rows)))
    for actual, expected in zip(actual_rows, expected_rows):
        for field in expected_fields:
            if actual.get(field, '') != expected.get(field, ''):
                mismatches.append((expected.get('filename'), field, actual.get(field, ''), expected.get(field, '')))
    print('checked_rows', len(expected_rows))
    print('mismatches', mismatches[:20])
    if mismatches:
        raise SystemExit(1)
finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
'@ | .\.venv\Scripts\python.exe -
```

### 影响 NeoSCA 的改动

若本机 Java 与 NeoSCA 依赖可用，应额外运行 NeoSCA 烟测。结果写入临时目录，不污染 `result/`。

```powershell
Set-Location 'e:\DMU\research\textAnalyse\index'
$tmp = New-Item -ItemType Directory -Path ([System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), [System.Guid]::NewGuid().ToString()))
.\.venv\Scripts\python.exe run_metrics.py --preset neosca --result-dir $tmp.FullName --no-resume
Remove-Item -Recurse -Force $tmp.FullName
```

### 依赖改动

- 新增 Python 依赖时，必须更新 `requirements.txt`。
- 安装包前确认使用工作区虚拟环境 `.venv/`。
- 不提交 Stanza 模型、UDPipe 模型、Java、NeoSCA 下载资源或任何大型外部资产。

## 代码库管理流程

- 开始任务前运行：

```powershell
Set-Location 'e:\DMU\research\textAnalyse\index'
git status --short
git log --oneline -3
```

- 不要回滚、删除或覆盖用户未要求修改的变更。
- 不要使用 `git reset --hard`、`git checkout -- <file>`、强制清理等破坏性命令，除非用户明确要求。
- 提交前必须完成与改动范围对应的检查，并在回复中说明验证结果。
- 只暂存与当前任务相关的文件。不要暂存 `.venv/`、`result/`、压缩包、大型语料、缓存或临时 LeoDD 目录。
- 用户没有明确要求提交时，不自动提交；若用户要求“上传至本地仓库”“提交”“保存版本”，再创建提交。
- 提交信息使用简短祈使句，示例：
  - `Add project agent guidelines`
  - `Refine configurable metric pipeline`
  - `Update documentation for single entry point`
- 不改写历史、不 rebase、不 squash、不 force push；本仓库当前只要求本地版本管理。

## 文档维护规则

- 面向用户的流程、依赖、配置和输出列发生变化时，必须同步更新 `README_CN.md` 和 `README.md`。
- `README_CN.md` 是主要中文说明；`README.md` 是英文对应版本。
- 长命令或回归脚本可以放在 `AGENTS.md` 中作为开发流程；README 中只保留用户运行项目所需的简明命令。

## 常见禁止事项

- 不要重新创建根目录兼容跳转脚本。
- 不要把生成结果作为默认提交内容。
- 不要把运行环境、模型文件、大型语料或外部工具源码纳入 Git。
- 不要为了通过检查而改动既有结果 CSV；结果不一致时应定位计算逻辑或配置差异。
- 不要在没有验证的情况下声称“结果一致”或“流程可用”。