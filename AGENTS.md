# Project Agent Guidelines

## Scope

These instructions apply to the whole repository. Use them together with `README_CN.md`, `README.md`, and `metrics_config.json`.

## Project Shape

- Keep `run_metrics.py` as the only root-level Python entry point.
- Keep metric implementations inside `metric_modules/`:
  - `custom_metrics.py`: custom MDD, NDD, MHDD, AlphaDepLength from Stanza CoNLL-U.
  - `leo_dd.py`: Python reimplementation of LeoDDcalculator with UDPipe.
  - `quansyn_metrics.py`: QuanSyn `depval` integration.
  - `neosca_metrics.py`: NeoSCA subprocess integration.
  - `pipeline.py`: orchestration, resume behavior, CSV writing, category traversal.
  - `config.py` and `fields.py`: method presets, defaults, and output columns.
- Do not reintroduce root-level compatibility wrappers such as `calculate_all_metrics.py`, `calculate_other_metrics.py`, or `calculate_neosca.py`.
- Treat `result/`, `*_results_dd/`, `.venv/`, archives, `treebanks/`, `combine_index/`, and `index/` as local/generated or external resources unless the user explicitly asks otherwise.

## Configuration Workflow

- Prefer `metrics_config.json` for default behavior and `run_metrics.py` flags for one-off runs.
- Method keys are `custom`, `leo`, `quansyn`, and `neosca`.
- When adding or renaming metrics, update all relevant places together:
  - metric implementation module
  - `metric_modules/fields.py`
  - `metrics_config.json` when defaults change
  - README usage/output documentation
- Keep `output_fields` aligned with enabled methods when a config is intended for reproducible comparisons.
- Use `leo.language_model_folder` for the UDPipe model directory. The default model path is `C:/english-ewt-ud-2.4-190531.udpipe`.

## Coding Standards

- Use Python 3.8+ compatible code. If using modern type syntax such as `str | None`, keep `from __future__ import annotations`.
- Preserve the current simple module style: small functions, explicit dictionaries, standard library first, third-party imports next, local imports last.
- Keep code comments sparse. Add comments only for non-obvious formulas, external tool quirks, or lifecycle issues such as UDPipe model ownership.
- Do not add one-letter variable names except for conventional local loops where clarity is unaffected.
- Keep user-facing CLI text and logs concise and in English unless the surrounding file is Chinese documentation.
- Do not hard-code new absolute paths except documented external tool/model defaults. Prefer config values.

## Validation Workflow

Run focused checks after code changes. On Windows PowerShell, use semicolons rather than shell-specific `&&` chains.

Minimum checks for Python changes:

```powershell
Set-Location 'e:\DMU\research\textAnalyse\index'
.\.venv\Scripts\python.exe -m compileall -q run_metrics.py metric_modules
.\.venv\Scripts\python.exe run_metrics.py --help
```

Regression check for changes affecting `custom`, `leo`, `quansyn`, config, or pipeline output:

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

For NeoSCA changes, also run a NeoSCA-focused smoke test when Java and NeoSCA dependencies are available:

```powershell
.\.venv\Scripts\python.exe run_metrics.py --preset neosca --result-dir <temp_dir> --no-resume
```

## Repository Management

- Start work with `git status --short` and inspect recent commits when needed.
- Do not commit unless the user explicitly asks for a commit.
- Stage only task-related files. Do not stage `.venv/`, `result/`, archives, external treebanks, generated caches, or temporary Leo folders.
- Before committing, run the relevant validation checks and include the result in the final response.
- Use short imperative commit messages, for example `Add project agent guidelines`.
- Never rewrite history, reset, or discard user changes unless the user explicitly asks for that operation.

## Documentation Rules

- Update `README_CN.md` and `README.md` together when user-facing workflow, configuration, dependencies, or output columns change.
- Keep `README_CN.md` as the primary Chinese user guide and `README.md` as the English counterpart.
- Avoid duplicating long implementation details in docs; point to `metrics_config.json` and `metric_modules/` where appropriate.

## Dependency Rules

- Use the workspace virtual environment at `.venv/` for local validation.
- When adding Python packages, update `requirements.txt` and verify imports with the selected workspace interpreter.
- External runtime assets, including Stanza models, the UDPipe `.udpipe` model, Java, and NeoSCA parser dependencies, are environment prerequisites and should not be committed.