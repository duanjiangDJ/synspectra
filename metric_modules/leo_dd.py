from __future__ import annotations

import csv
import math
import os
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass

from ufal.udpipe import Model, Pipeline, ProcessingError

from .parallel import memory_info_gb

_RAW_DEPENDENCY_FIELDS = [
    "sid",
    "token",
    "token_head",
    "dep_relation",
    "token_id",
    "head_token_id",
    "lemma",
    "upos",
]
_leo_worker_pipeline = None


@dataclass(frozen=True)
class DependencyRow:
    sid: int
    token: str
    token_head: str
    dep_relation: str
    token_id: int
    head_token_id: int
    lemma: str = ""
    upos: str = ""


@dataclass(frozen=True)
class UdpipePipeline:
    model: Model
    pipeline: Pipeline

    def process(self, text: str, error: ProcessingError) -> str:
        return self.pipeline.process(text, error)


def load_udpipe_pipeline(model_path: str = "C:/english-ewt-ud-2.4-190531.udpipe"):
    model = Model.load(model_path)
    if model is None:
        raise FileNotFoundError(f"UDPipe model could not be loaded: {model_path}")
    pipeline = Pipeline(model, "tokenize", Pipeline.DEFAULT, Pipeline.DEFAULT, "conllu")
    return UdpipePipeline(model=model, pipeline=pipeline)


def annotate_text(text: str, pipeline) -> list[DependencyRow]:
    error = ProcessingError()
    conllu = pipeline.process(text, error)
    if error.occurred():
        raise RuntimeError(error.message)

    rows: list[DependencyRow] = []
    sentence_id = 0
    sentence_tokens: list[tuple[int, str, str, str, str, int]] = []

    def flush_sentence() -> None:
        nonlocal sentence_id, sentence_tokens
        if not sentence_tokens:
            return
        sentence_id += 1
        token_by_id = {token_id: token for token_id, token, _, _, _, _ in sentence_tokens}
        for token_id, token, lemma, upos, dep_relation, head_token_id in sentence_tokens:
            rows.append(
                DependencyRow(
                    sid=sentence_id,
                    token=token,
                    token_head=token_by_id.get(head_token_id, ""),
                    dep_relation=dep_relation,
                    token_id=token_id,
                    head_token_id=head_token_id,
                    lemma=lemma,
                    upos=upos,
                )
            )
        sentence_tokens = []

    for line in conllu.splitlines():
        line = line.strip()
        if not line:
            flush_sentence()
            continue
        if line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) != 10 or "-" in parts[0] or "." in parts[0]:
            continue
        try:
            token_id = int(parts[0])
            head_token_id = int(parts[6])
        except ValueError:
            continue
        sentence_tokens.append((token_id, parts[1], parts[2], parts[3], parts[7], head_token_id))

    flush_sentence()
    return rows


def calculate_mdd_ndd_from_dependencies(rows: Iterable[DependencyRow]) -> tuple[float, float]:
    by_sentence: dict[int, list[DependencyRow]] = {}
    for row in rows:
        by_sentence.setdefault(row.sid, []).append(row)

    mdd_values: list[float] = []
    ndd_values: list[float] = []

    for sentence_rows in by_sentence.values():
        root_rows = [row for row in sentence_rows if row.dep_relation == "root"]
        if not root_rows:
            continue

        sentence_length = max(row.token_id for row in sentence_rows)
        dependency_distances = [
            abs(row.token_id - row.head_token_id)
            for row in sentence_rows
            if row.dep_relation not in ("root", "punct")
        ]
        if not dependency_distances:
            continue

        mdd = sum(dependency_distances) / len(dependency_distances)
        ndd = abs(math.log(mdd / math.sqrt(sentence_length * root_rows[0].token_id)))
        mdd_values.append(mdd)
        ndd_values.append(ndd)

    if not mdd_values or not ndd_values:
        return 0.0, 0.0

    return round(sum(mdd_values) / len(mdd_values), 4), round(sum(ndd_values) / len(ndd_values), 4)


def calculate_text_mdd_ndd(text: str, pipeline) -> tuple[float, float]:
    return calculate_mdd_ndd_from_dependencies(annotate_text(text, pipeline))


def _write_raw_dependencies_csv(raw_path: str, dependencies: list[DependencyRow]) -> None:
    with open(raw_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=_RAW_DEPENDENCY_FIELDS)
        writer.writeheader()
        for row in dependencies:
            writer.writerow(row.__dict__)


def _init_leo_worker(model_path: str) -> None:
    global _leo_worker_pipeline
    _leo_worker_pipeline = load_udpipe_pipeline(model_path)


def _process_leo_batch(tasks: list[tuple[str, str, str]]) -> list[tuple[str, float, float]]:
    if _leo_worker_pipeline is None:
        raise RuntimeError("UDPipe worker pipeline is not initialized.")
    results: list[tuple[str, float, float]] = []
    for filename, file_path, raw_path in tasks:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        dependencies = annotate_text(text, _leo_worker_pipeline)
        _write_raw_dependencies_csv(raw_path, dependencies)
        mdd, ndd = calculate_mdd_ndd_from_dependencies(dependencies)
        results.append((filename, mdd, ndd))
    return results


def calculate_folder_mdd_ndd(
    texts_folder: str,
    language_model_folder: str = "C:/",
    results_folder: str | None = None,
    progress_cb=None,
    model_file: str = "english-ewt-ud-2.4-190531.udpipe",
) -> tuple[dict[str, dict[str, float]], str]:
    model_path = os.path.join(language_model_folder, model_file)
    texts_folder_stripped = texts_folder.rstrip("/\\")
    results_folder = results_folder or f"{texts_folder_stripped}_results_dd"
    os.makedirs(results_folder, exist_ok=True)

    txt_files = sorted(name for name in os.listdir(texts_folder) if name.endswith(".txt"))
    total_files = len(txt_files)
    metrics: dict[str, dict[str, float]] = {}

    cpu_count = os.cpu_count() or 1
    _, avail_gb = memory_info_gb()
    ram_worker_cap = 2 if (avail_gb is not None and avail_gb < 2.0) else 8
    max_workers = min(cpu_count, ram_worker_cap, max(1, total_files // 16))
    ran_parallel = False
    if total_files >= 64 and max_workers > 1:
        tasks = [
            (
                filename,
                os.path.join(texts_folder, filename),
                os.path.join(results_folder, f"{os.path.splitext(filename)[0]}_raw_dependencies.csv"),
            )
            for filename in txt_files
        ]
        batch_size = max(16, min(64, (total_files + max_workers * 2 - 1) // (max_workers * 2)))
        batches = [tasks[i : i + batch_size] for i in range(0, total_files, batch_size)]
        completed = 0
        try:
            with ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=_init_leo_worker,
                initargs=(model_path,),
            ) as pool:
                futures = [pool.submit(_process_leo_batch, batch) for batch in batches]
                for future in as_completed(futures):
                    for filename, mdd, ndd in future.result():
                        metrics[filename] = {"MDD_Leo": mdd, "NDD_Leo": ndd}
                        completed += 1
                        if progress_cb is not None:
                            progress_cb(filename, completed, total_files)
            ran_parallel = True
        except (OSError, PermissionError):
            metrics.clear()

    if not ran_parallel:
        pipeline = load_udpipe_pipeline(model_path)
        for index, filename in enumerate(txt_files, start=1):
            file_path = os.path.join(texts_folder, filename)
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

            dependencies = annotate_text(text, pipeline)
            raw_path = os.path.join(results_folder, f"{os.path.splitext(filename)[0]}_raw_dependencies.csv")
            _write_raw_dependencies_csv(raw_path, dependencies)
            mdd, ndd = calculate_mdd_ndd_from_dependencies(dependencies)
            metrics[filename] = {"MDD_Leo": mdd, "NDD_Leo": ndd}
            if progress_cb is not None:
                progress_cb(filename, index, total_files)

    summary_rows = [
        {
            "file_id": os.path.splitext(filename)[0],
            "mdd": f"{metrics[filename]['MDD_Leo']:.4f}",
            "ndd": f"{metrics[filename]['NDD_Leo']:.4f}",
            "model": model_file,
        }
        for filename in txt_files
        if filename in metrics
    ]

    summary_path = os.path.join(results_folder, "0mdd_ndd_results.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["file_id", "mdd", "ndd", "model"])
        writer.writeheader()
        writer.writerows(summary_rows)

    return metrics, results_folder
