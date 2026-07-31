from __future__ import annotations

import csv
import os
import shutil
from typing import Any

import stanza

from .custom_metrics import compute_custom_metrics
from .fields import fields_for_methods
from .leo_dd import calculate_folder_mdd_ndd
from .neosca_metrics import compute_neosca_metrics
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
    print("\nConnecting to Stanza ...")
    nlp = stanza.Pipeline(
        "en",
        processors=stanza_config.get("processors", "tokenize,pos,lemma,depparse"),
        verbose=bool(stanza_config.get("verbose", False)),
        use_gpu=bool(stanza_config.get("use_gpu", False)),
    )
    print("Stanza connected successfully.")
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
            print(f"Loaded Leo metrics from existing file, total {len(metrics)} files.")
            return metrics, leo_results_dir
        except Exception as exc:
            print(f"Failed to read existing Leo results ({exc}), will recalculate.")
            shutil.rmtree(leo_results_dir, ignore_errors=True)

    print("No Leo results found, starting calculation...")
    leo_config = config.get("leo", {})
    try:
        return calculate_folder_mdd_ndd(
            texts_folder=category_path,
            language_model_folder=leo_config.get("language_model_folder", "C:/"),
            results_folder=leo_results_dir,
        )
    except Exception as exc:
        print(f"Leo Python calculation failed: {exc}")
        return {}, leo_results_dir


def output_fields_for_config(config: dict[str, Any], methods: dict[str, bool]) -> list[str]:
    configured_fields = config.get("output_fields")
    if configured_fields:
        return list(configured_fields)
    return fields_for_methods(methods, include_all_quansyn=bool(config.get("include_all_quansyn_fields", False)))


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
        print(f"Folder path {category_path} does not exist, skipping to the next folder.")
        return None

    txt_files_all = sorted(filename for filename in os.listdir(category_path) if filename.endswith(".txt"))
    processed_files: set[str] = set()
    existing_fieldnames: list[str] | None = None
    if config.get("resume", True):
        try:
            processed_files, existing_fieldnames = read_processed_files(output_csv)
            if processed_files:
                print(f"Found existing progress file, {len(processed_files)} files already processed.")
        except Exception as exc:
            print(f"Error reading progress file, restarting: {exc}")

    txt_files = [filename for filename in txt_files_all if filename not in processed_files]
    if not txt_files:
        print("All files have been processed, nothing to continue.")
        return output_csv

    leo_metrics: dict[str, dict[str, float]] = {}
    leo_results_dir = os.path.join(source_dir, f"{category_name}_results_dd")
    if methods["leo"]:
        leo_metrics, leo_results_dir = get_leo_metrics(category_path, source_dir, config)

    fieldnames = existing_fieldnames or output_fields_for_config(config, methods)
    file_mode = "a" if existing_fieldnames else "w"
    write_header = existing_fieldnames is None
    neosca_timeout = int(config.get("neosca", {}).get("timeout", 1000))
    needs_conllu = methods["custom"] or methods["quansyn"]

    with open(output_csv, file_mode, newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, restval="")
        if write_header:
            writer.writeheader()

        for txt_file in txt_files:
            file_path = os.path.join(category_path, txt_file)
            text_content = clean_text(extract_text_from_file(file_path))
            if not text_content:
                print(f"{txt_file}: text is empty, skipping")
                continue
            print(f"{txt_file}: {text_content[:30]}...")

            row: dict[str, Any] = {"filename": txt_file}
            conllu_str = text_to_conllu(text_content, nlp) if needs_conllu and nlp is not None else ""

            if methods["custom"]:
                print("Calculating custom metrics...\t", end=" ")
                row.update(compute_custom_metrics(conllu_str))
                print("Parsing completed.")
            if methods["leo"] and txt_file in leo_metrics:
                row.update(leo_metrics[txt_file])
            if methods["quansyn"]:
                print("Calculating QuanSyn metrics...\t", end=" ")
                row.update(compute_quansyn_text_metrics(conllu_str))
                print("Parsing completed.")
            if methods["neosca"]:
                print("Calculating NeoSCA metrics...\t", end=" ")
                row.update(compute_neosca_metrics(text_content, timeout=neosca_timeout))
                print("Parsing completed.")

            writer.writerow({field: row.get(field, "") for field in fieldnames})
            csvfile.flush()
            print(f"Write completed: {txt_file}")

    final_processed, _ = read_processed_files(output_csv)
    if methods["leo"]:
        if len(final_processed) == len(txt_files_all) and config.get("cleanup_leo_results", True):
            shutil.rmtree(leo_results_dir, ignore_errors=True)
            print(f"All files completed, Leo temporary folder {leo_results_dir} has been deleted.")
        elif len(final_processed) != len(txt_files_all):
            print(f"{len(txt_files_all) - len(final_processed)} files remaining unprocessed, keeping Leo results for resuming.")

    print(f"Folder {category_name} processing completed, results saved to {output_csv}")
    return output_csv


def run_pipeline(config: dict[str, Any], base_dir: str | None = None) -> list[str]:
    base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_dir = resolve_path(base_dir, config.get("source_dir", "source"))
    result_dir = resolve_path(base_dir, config.get("result_dir", "result"))
    os.makedirs(result_dir, exist_ok=True)

    if not os.path.exists(source_dir):
        print("Source folder not found.")
        return []

    methods = enabled_methods(config)
    nlp = load_stanza_pipeline(config) if methods["custom"] or methods["quansyn"] else None
    output_files: list[str] = []

    for subdir in [
        dirname
        for dirname in sorted(os.listdir(source_dir))
        if os.path.isdir(os.path.join(source_dir, dirname)) and not dirname.endswith("_results_dd")
    ]:
        print(f"\nStarting to process category: {subdir}")
        output_csv = process_category_folder(os.path.join(source_dir, subdir), result_dir, source_dir, config, nlp)
        if output_csv:
            output_files.append(output_csv)

    print("\nAll categories processed.")
    return output_files