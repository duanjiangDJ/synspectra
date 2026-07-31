from __future__ import annotations

import csv
import math
import os
from collections.abc import Iterable
from dataclasses import dataclass

from ufal.udpipe import Model, Pipeline, ProcessingError


@dataclass(frozen=True)
class DependencyRow:
    sid: int
    token: str
    token_head: str
    dep_relation: str
    token_id: int
    head_token_id: int


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
    sentence_tokens: list[tuple[int, str, str, int]] = []

    def flush_sentence() -> None:
        nonlocal sentence_id, sentence_tokens
        if not sentence_tokens:
            return
        sentence_id += 1
        token_by_id = {token_id: token for token_id, token, _, _ in sentence_tokens}
        for token_id, token, dep_relation, head_token_id in sentence_tokens:
            rows.append(
                DependencyRow(
                    sid=sentence_id,
                    token=token,
                    token_head=token_by_id.get(head_token_id, ""),
                    dep_relation=dep_relation,
                    token_id=token_id,
                    head_token_id=head_token_id,
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
        sentence_tokens.append((token_id, parts[1], parts[7], head_token_id))

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


def calculate_folder_mdd_ndd(
    texts_folder: str,
    language_model_folder: str = "C:/",
    results_folder: str | None = None,
) -> tuple[dict[str, dict[str, float]], str]:
    model_path = os.path.join(language_model_folder, "english-ewt-ud-2.4-190531.udpipe")
    pipeline = load_udpipe_pipeline(model_path)
    results_folder = results_folder or f"{texts_folder.rstrip('/\\')}_results_dd"
    os.makedirs(results_folder, exist_ok=True)

    metrics: dict[str, dict[str, float]] = {}
    summary_rows: list[dict[str, str]] = []
    txt_files = [name for name in os.listdir(texts_folder) if name.endswith(".txt")]

    for filename in txt_files:
        file_path = os.path.join(texts_folder, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        dependencies = annotate_text(text, pipeline)
        raw_path = os.path.join(results_folder, f"{os.path.splitext(filename)[0]}_raw_dependencies.csv")
        with open(raw_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=["sid", "token", "token_head", "dep_relation", "token_id", "head_token_id"],
            )
            writer.writeheader()
            for row in dependencies:
                writer.writerow(row.__dict__)

        mdd, ndd = calculate_mdd_ndd_from_dependencies(dependencies)
        file_id = os.path.splitext(filename)[0]
        metrics[filename] = {"MDD_Leo": mdd, "NDD_Leo": ndd}
        summary_rows.append({"file_id": file_id, "mdd": f"{mdd:.4f}", "ndd": f"{ndd:.4f}"})

    summary_path = os.path.join(results_folder, "0mdd_ndd_results.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["file_id", "mdd", "ndd"])
        writer.writeheader()
        writer.writerows(summary_rows)

    return metrics, results_folder