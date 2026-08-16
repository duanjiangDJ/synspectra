from __future__ import annotations

import csv
import os
import shutil
from typing import Any

import stanza

from . import event_logger
from .custom_metrics import compute_custom_metrics
from .fields import fields_for_methods
from .leo_dd import calculate_folder_mdd_ndd
from .neosca_metrics import NeoSCABatcher
from .parallel import parse_files_parallel
from .quansyn_metrics import compute_quansyn_text_metrics
from .stanza_conllu import text_to_conllu
from .text_utils import clean_text, extract_text_from_file


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


def load_stanza_pipeline(config: dict[str, Any]):
    stanza_config = config.get("stanza", {})
    event_logger.stage(
        "stanza",
        message="Loading Stanza models ...",
        human_message="\nLoading Stanza models ...",
    )
    nlp = stanza.Pipeline(
        "en",
        processors=stanza_config.get("processors", "tokenize,pos,lemma,depparse"),
        verbose=bool(stanza_config.get("verbose", False)),
        use_gpu=bool(stanza_config.get("use_gpu", False)),
        download_method=stanza_config.get("download_method"),
    )
    event_logger.log("info", "Stanza models loaded successfully.")
    return nlp


def read_processed_files(output_csv: str) -> tuple[set[str], list[str] | None]:
    processed_files: set[str] = set()
    if not os.path.exists(output_csv):
        return processed_files, None

    with open(output_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row.get("filename"):
                processed_files.add(row["filename"])
    return processed_files, fieldnames


def read_leo_cache(leo_csv_path: str) -> dict[str, dict[str, float]]:
    leo_metrics: dict[str, dict[str, float]] = {}
    with open(leo_csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            filename = f"{row['file_id']}.txt"
            leo_metrics[filename] = {
                "MDD_Leo": round(float(row["mdd"]), 4),
                "NDD_Leo": round(float(row["ndd"]), 4),
            }
    return leo_metrics


def get_leo_metrics(category_path: str, source_dir: str, config: dict[str, Any]) -> tuple[dict[str, dict[str, float]], str]:
    category_name = os.path.basename(category_path)
    leo_results_dir = os.path.join(source_dir, f"{category_name}_results_dd")
    leo_csv_path = os.path.join(leo_results_dir, "0mdd_ndd_results.csv")

    if os.path.exists(leo_csv_path):
        try:
            metrics = read_leo_cache(leo_csv_path)
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
    leo_config = config.get("leo", {})
    try:
        return calculate_folder_mdd_ndd(
            texts_folder=category_path,
            language_model_folder=leo_config.get("language_model_folder", "C:/"),
            results_folder=leo_results_dir,
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
    output_csv = os.path.join(output_dir, f"{category_name}{output_suffix}.csv")

    if not os.path.exists(category_path):
        event_logger.log(
            "warning",
            f"Folder path {category_path} does not exist, skipping to the next folder.",
        )
        return None

    txt_files_all = sorted(filename for filename in os.listdir(category_path) if filename.endswith(".txt"))
    processed_files: set[str] = set()
    existing_fieldnames: list[str] | None = None
    if config.get("resume", True):
        try:
            processed_files, existing_fieldnames = read_processed_files(output_csv)
            if processed_files:
                event_logger.log(
                    "info",
                    f"Found existing progress file, {len(processed_files)} files already processed.",
                )
        except Exception as exc:
            event_logger.log("warning", f"Error reading progress file, restarting: {exc}")

    txt_files = [filename for filename in txt_files_all if filename not in processed_files]
    if not txt_files:
        event_logger.log("info", "All files have been processed, nothing to continue.")
        return output_csv

    leo_metrics: dict[str, dict[str, float]] = {}
    leo_results_dir = os.path.join(source_dir, f"{category_name}_results_dd")
    if methods["leo"]:
        leo_metrics, leo_results_dir = get_leo_metrics(category_path, source_dir, config)

    fieldnames = existing_fieldnames or output_fields_for_config(config, methods)
    file_mode = "a" if existing_fieldnames else "w"
    write_header = existing_fieldnames is None

    stanza_config = config.get("stanza", {})
    workers = int(stanza_config.get("workers", 1) or 1)
    needs_conllu = methods["custom"] or methods["quansyn"]
    chunk_size = max(workers * 4, 4) if workers > 1 else 0

    neosca_config = config.get("neosca", {})
    neosca_timeout = int(neosca_config.get("timeout", 300))
    neosca_batch_size = int(neosca_config.get("batch_size", 10))
    neosca_max_length = neosca_config.get("max_length")
    if neosca_max_length is not None:
        neosca_max_length = int(neosca_max_length)
    batcher = (
        NeoSCABatcher(
            timeout=neosca_timeout,
            batch_size=neosca_batch_size,
            max_length=neosca_max_length,
        )
        if methods["neosca"]
        else None
    )

    with open(output_csv, file_mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, restval="")
        if write_header:
            writer.writeheader()

        written = len(txt_files_all) - len(txt_files)
        held_rows: list[tuple[str, dict[str, Any]]] = []

        def write_row(txt_file: str, row: dict[str, Any]) -> None:
            nonlocal written
            writer.writerow({field: row.get(field, "") for field in fieldnames})
            csvfile.flush()
            written += 1
            event_logger.progress(
                category_name,
                txt_file,
                "write",
                written,
                len(txt_files_all),
                human_message=f"Write completed: {txt_file}",
            )

        def finalize_held() -> None:
            for held_file, held_row in held_rows:
                if batcher is not None:
                    held_row.update(batcher.take(held_file))
                write_row(held_file, held_row)
            held_rows.clear()

        ranges = _chunk_ranges(len(txt_files), chunk_size) if chunk_size else [(0, len(txt_files))]
        for start, end in ranges:
            chunk = txt_files[start:end]
            conllu_map: dict[str, str] = {}
            if needs_conllu and workers > 1 and len(chunk) > 1:
                event_logger.stage(
                    "stanza",
                    message=f"Parsing {len(chunk)} files with {workers} workers",
                )
                written_before_chunk = written
                conllu_map = parse_files_parallel(
                    [os.path.join(category_path, name) for name in chunk],
                    stanza_config,
                    workers,
                    on_progress=lambda filepath, done_in_chunk: event_logger.progress(
                        category_name,
                        os.path.basename(filepath),
                        "stanza",
                        written_before_chunk + done_in_chunk,
                        len(txt_files_all),
                    ),
                )

            for txt_file in chunk:
                file_path = os.path.join(category_path, txt_file)
                text_content = clean_text(extract_text_from_file(file_path))
                if not text_content:
                    event_logger.log("warning", f"{txt_file}: text is empty, skipping")
                    continue
                event_logger.stage(
                    "file",
                    message=f"{txt_file}: {text_content[:30]}...",
                )

                row: dict[str, Any] = {"filename": txt_file}
                if needs_conllu:
                    if file_path in conllu_map:
                        conllu_str = conllu_map[file_path]
                    elif nlp is not None:
                        conllu_str = text_to_conllu(text_content, nlp)
                    else:
                        conllu_str = ""

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
                    write_row(txt_file, row)

        if batcher is not None and held_rows:
            batcher.flush()
            event_logger.human("Parsing completed.")
            finalize_held()

    final_processed, _ = read_processed_files(output_csv)
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
        f"Folder {category_name} processing completed, results saved to {output_csv}",
    )
    return output_csv


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
    needs_stanza = methods["custom"] or methods["quansyn"]
    workers = int(config.get("stanza", {}).get("workers", 1) or 1)
    # With parallel workers each worker process loads its own Stanza copy;
    # the main process pipeline is only needed for the serial path.
    nlp = load_stanza_pipeline(config) if needs_stanza and workers <= 1 else None
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
        output_csv = process_category_folder(os.path.join(source_dir, subdir), result_dir, source_dir, config, nlp)
        if output_csv:
            output_files.append(output_csv)

    event_logger.log("info", "\nAll categories processed.")
    return output_files
