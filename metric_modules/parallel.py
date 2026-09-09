from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable

_worker_nlp = None


def _init_worker(stanza_config: dict[str, Any]) -> None:
    """Per-worker initializer: one Stanza pipeline per process."""
    global _worker_nlp
    try:
        import torch  # type: ignore

        threads = int(os.environ.get("SYNM_TORCH_THREADS", "2"))
        torch.set_num_threads(max(1, threads))
    except Exception:
        pass
    import stanza

    _worker_nlp = stanza.Pipeline(
        stanza_config.get("language", "en"),
        processors=stanza_config.get("processors", "tokenize,pos,lemma,depparse"),
        package=stanza_config.get("package", "default"),
        verbose=False,
        use_gpu=bool(stanza_config.get("use_gpu", False)),
        download_method=stanza_config.get("download_method"),
    )


def _parse_file_worker(filepath: str) -> str:
    """Parses one text file and returns its CoNLL-U (empty on failure).

    Workers never touch event_logger: any output here would corrupt the
    main process JSONL event stream.
    """
    global _worker_nlp
    if _worker_nlp is None:
        return ""
    try:
        from .text_utils import clean_text, extract_text_from_file

        text = clean_text(extract_text_from_file(filepath))
        if not text:
            return ""
        doc = _worker_nlp(text)
        conllu_lines: list[str] = []
        for sent in doc.sentences:
            for word in sent.words:
                line = (
                    f"{word.id}\t{word.text}\t{word.lemma}\t{word.upos}\t"
                    f"{word.xpos if word.xpos else chr(95)}\t"
                    f"{word.feats if word.feats else chr(95)}\t"
                    f"{word.head}\t{word.deprel}\t_\t_"
                )
                conllu_lines.append(line)
            conllu_lines.append("")
        return "\n".join(conllu_lines)
    except Exception:
        return ""


def create_process_pool(
    stanza_config: dict[str, Any],
    workers: int,
) -> ProcessPoolExecutor:
    """Creates a worker pool whose processes load their Stanza models once.

    Loading Stanza costs seconds per process, so the caller keeps one pool per
    category instead of paying the cost for every chunk.
    """
    return ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_worker,
        initargs=(stanza_config,),
    )


def parse_files_parallel(
    filepaths: list[str],
    stanza_config: dict[str, Any],
    workers: int,
    on_progress: Callable[[str, int], None] | None = None,
    pool: ProcessPoolExecutor | None = None,
) -> dict[str, str]:
    """Parses files across N worker processes; returns {filepath: conllu}.

    on_progress(filepath, completed_in_chunk) fires in the main process as
    each worker finishes a file, so the UI can stream live progress during
    the parallel phase instead of freezing until the chunk ends. When a
    ``pool`` is supplied it is reused and not shut down here.
    """
    if workers <= 1 or len(filepaths) < 2:
        # Serial fallback runs inside the main process to avoid fork cost
        # for tiny chunks; the caller passes its own pipeline in that case.
        return {}
    own_pool = pool is None
    if pool is None:
        pool = create_process_pool(stanza_config, workers)
    results: dict[str, str] = {}
    try:
        futures = {
            pool.submit(_parse_file_worker, filepath): filepath
            for filepath in filepaths
        }
        completed = 0
        for future in as_completed(futures):
            filepath = futures[future]
            try:
                results[filepath] = future.result()
            except Exception:
                results[filepath] = ""
            completed += 1
            if on_progress is not None:
                on_progress(filepath, completed)
    finally:
        if own_pool:
            pool.shutdown()
    return results
