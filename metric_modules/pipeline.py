from __future__ import annotations

import contextlib
import csv
import os
import shutil
import time
from typing import Any

import stanza

from . import event_logger
from .config import category_language, resolve_language_profile
from .custom_metrics import compute_custom_metrics
from .dependency_export import (
    extract_stanza_dependencies,
    read_existing_workbook,
    read_udpipe_raw_csv,
    write_category_workbook,
)
from .fields import fields_for_methods, filter_fields_for_methods
from .leo_dd import calculate_folder_mdd_ndd
from .neosca_metrics import NeoSCABatcher
from .parallel import create_process_pool, parse_files_parallel, resolve_effective_workers
from .quansyn_metrics import compute_quansyn_text_metrics
from .stanza_conllu import text_to_conllu, texts_to_conllu_batch
from .text_utils import clean_text, extract_text_from_file

# Serial runs load one Stanza pipeline per language profile and keep it around,
# so a mixed-language corpus does not reload the models for every category.
_STANZA_PIPELINES: dict[tuple[str, str, str], Any] = {}


def resolve_path(base_dir: str, path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(base_dir, path)


def enabled_methods(config: dict[str, Any]) -> dict[str, bool]:
    methods = config.get("methods", {})
    return {
        "custom": bool(methods.get("custom", False)),
        "leo": bool(methods.get("leo", False)),
        "quansyn": bool(methods.get("quansyn", False)),
        "neosca": bool(methods.get("neosca", False)),
    }


def category_settings(
    config: dict[str, Any],
    methods: dict[str, bool],
    category_name: str,
) -> tuple[str, dict[str, bool], dict[str, Any], dict[str, Any], list[str]]:
    """Resolves the language profile of one category into concrete settings.

    Returns (language, effective methods, stanza config, leo config,
    methods disabled for this language).
    """
    language = category_language(config, category_name)
    profile = resolve_language_profile(config, language)
    stanza_config = {**config.get("stanza", {}), **profile.get("stanza", {})}
    leo_config = {**config.get("leo", {}), **profile.get("leo", {})}
    effective = dict(methods)
    disabled: list[str] = []
    for method in profile.get("disabled_methods", []):
        if effective.get(method, False):
            effective[method] = False
            disabled.append(method)
    return language, effective, stanza_config, leo_config, disabled


def load_stanza_pipeline(config: dict[str, Any], stanza_config: dict[str, Any] | None = None):
    if stanza_config is None:
        stanza_config = config.get("stanza", {})
    key = (
        str(stanza_config.get("language", "en")),
        str(stanza_config.get("processors", "tokenize,pos,lemma,depparse")),
        str(stanza_config.get("package", "default")),
    )
    cached = _STANZA_PIPELINES.get(key)
    if cached is not None:
        return cached
    event_logger.stage(
        "stanza",
        message="Loading Stanza models ...",
        human_message="\nLoading Stanza models ...",
    )
    nlp = stanza.Pipeline(
        stanza_config.get("language", "en"),
        processors=stanza_config.get("processors", "tokenize,pos,lemma,depparse"),
        package=stanza_config.get("package", "default"),
        verbose=bool(stanza_config.get("verbose", False)),
        use_gpu=bool(stanza_config.get("use_gpu", False)),
        download_method=stanza_config.get("download_method"),
    )
    _STANZA_PIPELINES[key] = nlp
    event_logger.log("info", "Stanza models loaded successfully.")
    return nlp


def read_leo_cache(leo_csv_path: str, model_file: str | None = None) -> dict[str, dict[str, float]]:
    """Reads cached Leo results, refusing numbers produced by another model.

    Switching a category's language between runs must not reuse MDD_Leo/NDD_Leo
    computed with the previous language's UDPipe model.
    """
    leo_metrics: dict[str, dict[str, float]] = {}
    with open(leo_csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if model_file is not None and row.get("model") != model_file:
                raise ValueError(
                    f"cache was produced with {row.get('model') or 'an unknown model'}, "
                    f"expected {model_file}"
                )
            filename = f"{row['file_id']}.txt"
            leo_metrics[filename] = {
                "MDD_Leo": round(float(row["mdd"]), 4),
                "NDD_Leo": round(float(row["ndd"]), 4),
            }
    return leo_metrics


def get_leo_metrics(
    category_path: str,
    source_dir: str,
    config: dict[str, Any],
    leo_config: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, float]], str]:
    category_name = os.path.basename(category_path)
    leo_results_dir = os.path.join(source_dir, f"{category_name}_results_dd")
    leo_csv_path = os.path.join(leo_results_dir, "0mdd_ndd_results.csv")
    if leo_config is None:
        leo_config = config.get("leo", {})
    model_file = leo_config.get("model_file", "english-ewt-ud-2.4-190531.udpipe")

    if os.path.exists(leo_csv_path):
        try:
            metrics = read_leo_cache(leo_csv_path, model_file=model_file)
            event_logger.log(
                "info",
                f"Loaded Leo metrics from existing file, total {len(metrics)} files.",
            )
            return metrics, leo_results_dir
        except Exception as exc:
            event_logger.log(
                "warning",
                f"Failed to read existing Leo results ({exc}), will recalculate.",
            )
            shutil.rmtree(leo_results_dir, ignore_errors=True)

    event_logger.log("info", "No Leo results found, starting calculation...")
    event_logger.stage(
        "leo",
        message=f"Calculating Leo metrics for {category_name}",
        human_message=f"Calculating Leo metrics for {category_name}...",
    )
    try:
        return calculate_folder_mdd_ndd(
            texts_folder=category_path,
            language_model_folder=leo_config.get("language_model_folder", "C:/"),
            results_folder=leo_results_dir,
            model_file=model_file,
            progress_cb=lambda filename, done, total: event_logger.progress(
                category_name, filename, "leo", done, total
            ),
        )
    except Exception as exc:
        event_logger.error(
            "LEO_CALC_FAILED",
            "Leo Python calculation failed",
            str(exc),
            "Check the UDPipe model path and file permissions.",
        )
        return {}, leo_results_dir


def output_fields_for_config(config: dict[str, Any], methods: dict[str, bool]) -> list[str]:
    configured_fields = config.get("output_fields")
    if configured_fields:
        return list(configured_fields)
    return fields_for_methods(methods, include_all_quansyn=bool(config.get("include_all_quansyn_fields", False)))


def _chunk_ranges(total: int, chunk_size: int) -> list[tuple[int, int]]:
    """Splits [0, total) into ranges; the final range is merged into the
    previous one when it would contain a single item (parallel workers
    need at least two files to be worth spawning)."""
    ranges: list[tuple[int, int]] = []
    index = 0
    while index < total:
        end = min(index + chunk_size, total)
        if end - index < 2 and ranges:
            ranges[-1] = (ranges[-1][0], end)
        else:
            ranges.append((index, end))
        index = end
    return ranges or [(0, total)]


def process_category_folder(
    category_path: str,
    output_dir: str,
    source_dir: str,
    config: dict[str, Any],
    nlp=None,
) -> str | None:
    methods = enabled_methods(config)
    category_name = os.path.basename(category_path)
    output_suffix = config.get("output_suffix", "")
    output_xlsx = os.path.join(output_dir, f"{category_name}{output_suffix}.xlsx")

    if not os.path.exists(category_path):
        event_logger.log(
            "warning",
            f"Folder path {category_path} does not exist, skipping to the next folder.",
        )
        return None

    language, methods, stanza_config, leo_config, disabled_methods = category_settings(
        config, methods, category_name
    )
    if disabled_methods:
        event_logger.log(
            "warning",
            f"Language '{language}': {', '.join(disabled_methods)} not supported, "
            f"skipped for category {category_name}.",
        )

    txt_files_all = sorted(filename for filename in os.listdir(category_path) if filename.endswith(".txt"))
    processed_files: set[str] = set()
    existing_fieldnames: list[str] | None = None
    metric_rows: list[dict[str, Any]] = []
    existing_stanza_rows: list[list[Any]] | None = None
    existing_udpipe_rows: list[list[Any]] | None = None

    if config.get("resume", True):
        try:
            (
                processed_files,
                existing_fieldnames,
                metric_rows,
                existing_stanza_rows,
                existing_udpipe_rows,
            ) = read_existing_workbook(output_xlsx)
            if processed_files:
                event_logger.log(
                    "info",
                    f"Found existing progress file, {len(processed_files)} files already processed.",
                )
        except Exception as exc:
            event_logger.log("warning", f"Error reading progress file, restarting: {exc}")
            processed_files = set()
            existing_fieldnames = None
            metric_rows = []
            existing_stanza_rows = None
            existing_udpipe_rows = None

    export_deps = bool(config.get("export_dependencies", True))
    needs_conllu = methods["custom"] or methods["quansyn"]
    need_stanza_sheet = export_deps and needs_conllu
    need_udpipe_sheet = export_deps and methods["leo"]
    stanza_missing_sheet = need_stanza_sheet and existing_stanza_rows is None
    udpipe_missing_sheet = need_udpipe_sheet and existing_udpipe_rows is None

    txt_files = [filename for filename in txt_files_all if filename not in processed_files]
    if not txt_files and not (stanza_missing_sheet or udpipe_missing_sheet):
        event_logger.log("info", "All files have been processed, nothing to continue.")
        return output_xlsx
    if not txt_files:
        event_logger.log("info", "All metric rows already processed; completing dependency sheets.")

    leo_metrics: dict[str, dict[str, float]] = {}
    leo_results_dir = os.path.join(source_dir, f"{category_name}_results_dd")
    if methods["leo"] and (txt_files or udpipe_missing_sheet):
        leo_metrics, leo_results_dir = get_leo_metrics(category_path, source_dir, config, leo_config)

    fieldnames = existing_fieldnames or filter_fields_for_methods(
        output_fields_for_config(config, methods), methods
    )

    requested_workers = int(stanza_config.get("workers", 1) or 1)
    use_gpu = bool(stanza_config.get("use_gpu", False))
    workers = resolve_effective_workers(requested_workers, use_gpu=use_gpu)
    if workers < requested_workers:
        event_logger.log(
            "info",
            f"Adjusted Stanza workers from {requested_workers} to {workers} based on available hardware.",
        )
    chunk_size = max(workers * 32, 64) if workers > 1 else 64
    if needs_conllu and workers <= 1 and nlp is None:
        nlp = load_stanza_pipeline(config, stanza_config)

    neosca_config = config.get("neosca", {})
    neosca_timeout = int(neosca_config.get("timeout", 1800))
    neosca_batch_size = int(neosca_config.get("batch_size", 2))
    neosca_words_per_second = int(neosca_config.get("words_per_second", 15))
    neosca_max_length = neosca_config.get("max_length")
    if neosca_max_length is not None:
        neosca_max_length = int(neosca_max_length)
    batcher = (
        NeoSCABatcher(
            timeout=neosca_timeout,
            batch_size=neosca_batch_size,
            max_length=neosca_max_length,
            words_per_second=neosca_words_per_second,
        )
        if methods["neosca"] and txt_files
        else None
    )

    stanza_rows_by_file: dict[str, list[list[Any]]] = {}
    if existing_stanza_rows is not None:
        for srow in existing_stanza_rows:
            if srow:
                stanza_rows_by_file.setdefault(str(srow[0]), []).append(srow)

    files_to_parse_count = len(txt_files_all) if stanza_missing_sheet else len(txt_files)

    with contextlib.ExitStack() as stack:
        # One worker pool per category: the workers keep their Stanza models
        # loaded across chunks instead of reloading them every chunk.
        parse_pool = None
        if needs_conllu and workers > 1 and chunk_size and files_to_parse_count > 1:
            try:
                parse_pool = stack.enter_context(create_process_pool(stanza_config, workers))
            except (OSError, PermissionError):
                workers = 1
                parse_pool = None
                if nlp is None:
                    nlp = load_stanza_pipeline(config, stanza_config)

        if txt_files:
            written = len(txt_files_all) - len(txt_files)
            held_rows: list[tuple[str, dict[str, Any]]] = []
            dirty_metrics = False
            rows_since_flush = 0
            last_flush_time = time.monotonic()

            def record_row(txt_file: str, row: dict[str, Any]) -> None:
                nonlocal written, dirty_metrics, rows_since_flush
                metric_rows.append({field: row.get(field, "") for field in fieldnames})
                dirty_metrics = True
                rows_since_flush += 1
                written += 1
                event_logger.progress(
                    category_name,
                    txt_file,
                    "write",
                    written,
                    len(txt_files_all),
                    human_message=f"Write completed: {txt_file}",
                )

            def flush_progress_workbook(force: bool = False) -> None:
                nonlocal dirty_metrics, rows_since_flush, last_flush_time
                if not dirty_metrics:
                    return
                if not force and rows_since_flush < 500 and (time.monotonic() - last_flush_time) < 60.0:
                    return
                write_category_workbook(output_xlsx, fieldnames, metric_rows, None, None)
                dirty_metrics = False
                rows_since_flush = 0
                last_flush_time = time.monotonic()

            def finalize_held() -> None:
                for held_file, held_row in held_rows:
                    if batcher is not None:
                        held_row.update(batcher.take(held_file))
                    record_row(held_file, held_row)
                held_rows.clear()
                flush_progress_workbook()

            ranges = _chunk_ranges(len(txt_files), chunk_size) if chunk_size else [(0, len(txt_files))]
            for start, end in ranges:
                chunk = txt_files[start:end]
                conllu_map: dict[str, str] = {}
                if needs_conllu and parse_pool is not None and workers > 1 and len(chunk) > 1:
                    event_logger.stage(
                        "stanza",
                        message=f"Parsing {len(chunk)} files with {workers} workers",
                    )
                    written_before_chunk = written
                    conllu_map = parse_files_parallel(
                        [os.path.join(category_path, name) for name in chunk],
                        stanza_config,
                        workers,
                        pool=parse_pool,
                        on_progress=lambda filepath, done_in_chunk: event_logger.progress(
                            category_name,
                            os.path.basename(filepath),
                            "stanza",
                            written_before_chunk + done_in_chunk,
                            len(txt_files_all),
                        ),
                    )
                elif needs_conllu and len(chunk) > 1:
                    if nlp is None:
                        nlp = load_stanza_pipeline(config, stanza_config)
                    chunk_paths = [os.path.join(category_path, name) for name in chunk]
                    chunk_texts = [clean_text(extract_text_from_file(fp)) for fp in chunk_paths]
                    for fp, conllu in zip(chunk_paths, texts_to_conllu_batch(chunk_texts, nlp)):
                        conllu_map[fp] = conllu

                for txt_file in chunk:
                    file_path = os.path.join(category_path, txt_file)
                    text_content = clean_text(extract_text_from_file(file_path))
                    if not text_content:
                        event_logger.log("warning", f"{txt_file}: text is empty, skipping")
                        if need_stanza_sheet:
                            stanza_rows_by_file[txt_file] = []
                        continue
                    event_logger.stage(
                        "file",
                        message=f"{txt_file}: {text_content[:30]}...",
                    )

                    row: dict[str, Any] = {"filename": txt_file}
                    if needs_conllu:
                        if conllu_map.get(file_path):
                            conllu_str = conllu_map[file_path]
                        else:
                            # Not parsed by a worker (single-file chunk, or the
                            # worker failed): parse here instead of silently
                            # writing zero-valued metrics.
                            if nlp is None:
                                nlp = load_stanza_pipeline(config, stanza_config)
                            conllu_str = text_to_conllu(text_content, nlp)
                        if need_stanza_sheet:
                            stanza_rows_by_file[txt_file] = extract_stanza_dependencies(txt_file, conllu_str)

                    if methods["custom"]:
                        event_logger.stage("custom")
                        event_logger.human("Calculating custom metrics...\t", end=" ")
                        row.update(compute_custom_metrics(conllu_str))
                        event_logger.human("Parsing completed.")
                    if methods["leo"] and txt_file in leo_metrics:
                        event_logger.stage("leo")
                        row.update(leo_metrics[txt_file])
                    if methods["quansyn"]:
                        event_logger.stage("quansyn")
                        event_logger.human("Calculating QuanSyn metrics...\t", end=" ")
                        row.update(compute_quansyn_text_metrics(conllu_str))
                        event_logger.human("Parsing completed.")
                    if batcher is not None:
                        event_logger.stage("neosca")
                        event_logger.human("Calculating NeoSCA metrics...\t", end=" ")
                        flushed = batcher.submit(txt_file, text_content)
                        held_rows.append((txt_file, row))
                        if flushed:
                            event_logger.human("Parsing completed.")
                            finalize_held()
                    else:
                        record_row(txt_file, row)

                if batcher is None and (need_stanza_sheet or need_udpipe_sheet or end < len(txt_files)):
                    flush_progress_workbook()

            if batcher is not None and held_rows:
                batcher.flush()
                event_logger.human("Parsing completed.")
                finalize_held()

        if need_stanza_sheet:
            missing_for_export = [
                filename for filename in txt_files_all if filename not in stanza_rows_by_file
            ]
            if missing_for_export:
                extra_conllu: dict[str, str] = {}
                if parse_pool is not None and len(missing_for_export) > 1:
                    event_logger.stage(
                        "stanza",
                        message=f"Parsing {len(missing_for_export)} resumed files with {workers} workers",
                    )
                    extra_conllu = parse_files_parallel(
                        [os.path.join(category_path, name) for name in missing_for_export],
                        stanza_config,
                        workers,
                        pool=parse_pool,
                    )
                elif len(missing_for_export) > 1:
                    if nlp is None:
                        nlp = load_stanza_pipeline(config, stanza_config)
                    missing_paths = [os.path.join(category_path, name) for name in missing_for_export]
                    missing_texts = [clean_text(extract_text_from_file(fp)) for fp in missing_paths]
                    for fp, conllu in zip(missing_paths, texts_to_conllu_batch(missing_texts, nlp)):
                        extra_conllu[fp] = conllu
                for txt_file in missing_for_export:
                    file_path = os.path.join(category_path, txt_file)
                    if extra_conllu.get(file_path):
                        stanza_rows_by_file[txt_file] = extract_stanza_dependencies(
                            txt_file, extra_conllu[file_path]
                        )
                        continue
                    text_content = clean_text(extract_text_from_file(file_path))
                    if not text_content:
                        stanza_rows_by_file[txt_file] = []
                        continue
                    if nlp is None:
                        nlp = load_stanza_pipeline(config, stanza_config)
                    stanza_rows_by_file[txt_file] = extract_stanza_dependencies(
                        txt_file, text_to_conllu(text_content, nlp)
                    )

    stanza_rows: list[list[Any]] | None = None
    if need_stanza_sheet:
        stanza_rows = []
        for txt_file in txt_files_all:
            stanza_rows.extend(stanza_rows_by_file.get(txt_file, []))

    udpipe_rows: list[list[Any]] | None = None
    if need_udpipe_sheet:
        if os.path.isdir(leo_results_dir):
            udpipe_rows = []
            for txt_file in txt_files_all:
                raw_csv_path = os.path.join(
                    leo_results_dir,
                    f"{os.path.splitext(txt_file)[0]}_raw_dependencies.csv",
                )
                udpipe_rows.extend(read_udpipe_raw_csv(txt_file, raw_csv_path))
        elif existing_udpipe_rows is not None:
            udpipe_rows = existing_udpipe_rows
        else:
            udpipe_rows = []

    if metric_rows or stanza_rows is not None or udpipe_rows is not None:
        write_category_workbook(output_xlsx, fieldnames, metric_rows, stanza_rows, udpipe_rows)

    final_processed = {
        str(item.get("filename", ""))
        for item in metric_rows
        if item.get("filename")
    }
    if methods["leo"]:
        if len(final_processed) == len(txt_files_all) and config.get("cleanup_leo_results", True):
            shutil.rmtree(leo_results_dir, ignore_errors=True)
            event_logger.log(
                "info",
                f"All files completed, Leo temporary folder {leo_results_dir} has been deleted.",
            )
        elif len(final_processed) != len(txt_files_all):
            event_logger.log(
                "info",
                f"{len(txt_files_all) - len(final_processed)} files remaining unprocessed, keeping Leo results for resuming.",
            )

    event_logger.log(
        "info",
        f"Folder {category_name} processing completed, results saved to {output_xlsx}",
    )
    return output_xlsx


def run_pipeline(config: dict[str, Any], base_dir: str | None = None) -> list[str]:
    base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_dir = resolve_path(base_dir, config.get("source_dir", "source"))
    result_dir = resolve_path(base_dir, config.get("result_dir", "result"))
    os.makedirs(result_dir, exist_ok=True)

    if not os.path.exists(source_dir):
        event_logger.error(
            "SOURCE_NOT_FOUND",
            "Source folder not found.",
            source_dir,
            "Select a valid input directory.",
        )
        return []

    methods = enabled_methods(config)
    # With parallel workers each worker process loads its own Stanza copy; the
    # serial path loads one pipeline per language inside the category loop,
    # because categories may use different languages.
    output_files: list[str] = []

    for subdir in [
        dirname
        for dirname in sorted(os.listdir(source_dir))
        if os.path.isdir(os.path.join(source_dir, dirname)) and not dirname.endswith("_results_dd")
    ]:
        event_logger.stage(
            "category",
            message=f"Starting to process category: {subdir}",
            human_message=f"\nStarting to process category: {subdir}",
        )
        output_csv = process_category_folder(os.path.join(source_dir, subdir), result_dir, source_dir, config)
        if output_csv:
            output_files.append(output_csv)

    event_logger.log("info", "\nAll categories processed.")
    return output_files
