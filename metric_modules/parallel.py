from __future__ import annotations

import ctypes
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable

from .stanza_conllu import MAX_BATCH_CHARS, doc_to_conllu

_worker_nlp = None


def memory_info_gb() -> tuple[float | None, float | None]:
    """Returns (total_gb, available_gb) without external dependencies."""
    try:
        if sys.platform == "win32":
            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                gb = 1024.0 ** 3
                return stat.ullTotalPhys / gb, stat.ullAvailPhys / gb
        elif sys.platform.startswith("linux"):
            mem_total_kb: int | None = None
            mem_avail_kb: int | None = None
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail_kb = int(line.split()[1])
            gb_kb = 1024.0 ** 2
            return (
                mem_total_kb / gb_kb if mem_total_kb is not None else None,
                mem_avail_kb / gb_kb if mem_avail_kb is not None else None,
            )
        elif sys.platform == "darwin":
            page_size = os.sysconf("SC_PAGE_SIZE")
            phys_pages = os.sysconf("SC_PHYS_PAGES")
            if page_size > 0 and phys_pages > 0:
                return (page_size * phys_pages) / (1024.0 ** 3), None
    except Exception:
        pass
    return None, None


def resolve_effective_workers(
    requested_workers: int,
    use_gpu: bool = False,
    cpu_count: int | None = None,
    mem_info: tuple[float | None, float | None] | None = None,
) -> int:
    """Clamps Stanza worker processes to what the host CPU, RAM, and GPU support."""
    if use_gpu or requested_workers <= 1:
        return 1
    cpus = cpu_count if cpu_count is not None else (os.cpu_count() or 2)
    cpu_cap = max(1, cpus // 2) if cpus >= 4 else max(1, cpus)

    total_gb, avail_gb = mem_info if mem_info is not None else memory_info_gb()
    if avail_gb is not None and avail_gb < 3.0:
        return 1
    ram_cap = requested_workers
    if total_gb is not None:
        ram_cap = max(1, int((total_gb - 2.0) // 2.5))

    return max(1, min(requested_workers, cpu_cap, ram_cap))


def _init_worker(stanza_config: dict[str, Any], workers: int = 1) -> None:
    """Per-worker initializer: one Stanza pipeline per process."""
    global _worker_nlp
    try:
        import torch  # type: ignore

        env_threads = os.environ.get("SYNM_TORCH_THREADS")
        if env_threads is not None:
            threads = max(1, int(env_threads))
        else:
            threads = max(1, min(8, (os.cpu_count() or 4) // max(1, workers)))
        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(1)
        except Exception:
            pass
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
        return doc_to_conllu(_worker_nlp(text))
    except Exception:
        return ""


def _parse_batch_worker(filepaths: list[str]) -> dict[str, str]:
    """Parses a batch of text files via Stanza bulk_process within a char budget."""
    global _worker_nlp
    if _worker_nlp is None:
        return {fp: "" for fp in filepaths}

    import stanza
    from .text_utils import clean_text, extract_text_from_file

    results: dict[str, str] = {}
    non_empty_paths: list[str] = []
    non_empty_texts: list[str] = []
    for fp in filepaths:
        try:
            text = clean_text(extract_text_from_file(fp))
        except Exception:
            text = ""
        if not text:
            results[fp] = ""
        else:
            non_empty_paths.append(fp)
            non_empty_texts.append(text)

    if not non_empty_paths:
        return results

    sub_batches: list[list[tuple[str, str]]] = []
    current_batch: list[tuple[str, str]] = []
    current_chars = 0
    for fp, text in zip(non_empty_paths, non_empty_texts):
        if current_batch and (
            len(current_batch) >= 32 or current_chars + len(text) > MAX_BATCH_CHARS
        ):
            sub_batches.append(current_batch)
            current_batch = []
            current_chars = 0
        current_batch.append((fp, text))
        current_chars += len(text)
    if current_batch:
        sub_batches.append(current_batch)

    for sub in sub_batches:
        if len(sub) == 1:
            fp, text = sub[0]
            try:
                results[fp] = doc_to_conllu(_worker_nlp(text))
            except Exception:
                results[fp] = ""
            continue
        try:
            docs = [stanza.Document([], text=text) for _, text in sub]
            parsed_docs = _worker_nlp.bulk_process(docs)
            for (fp, _), doc in zip(sub, parsed_docs):
                results[fp] = doc_to_conllu(doc)
        except Exception:
            for fp, text in sub:
                try:
                    results[fp] = doc_to_conllu(_worker_nlp(text))
                except Exception:
                    results[fp] = ""
    return results


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
        initargs=(stanza_config, workers),
    )


def parse_files_parallel(
    filepaths: list[str],
    stanza_config: dict[str, Any],
    workers: int,
    on_progress: Callable[[str, int], None] | None = None,
    pool: ProcessPoolExecutor | None = None,
) -> dict[str, str]:
    """Parses files across N worker processes using bulk_process; returns {filepath: conllu}.

    on_progress(filepath, completed_in_chunk) fires in the main process as
    each sub-batch finishes, so the UI can stream live progress during
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

    batch_size = max(1, min(32, (len(filepaths) + workers * 2 - 1) // (workers * 2)))
    batches = [
        filepaths[i : i + batch_size]
        for i in range(0, len(filepaths), batch_size)
    ]

    results: dict[str, str] = {}
    try:
        futures = {
            pool.submit(_parse_batch_worker, batch): batch
            for batch in batches
        }
        completed = 0
        for future in as_completed(futures):
            batch = futures[future]
            try:
                batch_results = future.result()
                results.update(batch_results)
            except Exception:
                for fp in batch:
                    results[fp] = ""
            completed += len(batch)
            if on_progress is not None:
                on_progress(batch[-1], completed)
    finally:
        if own_pool:
            pool.shutdown()
    return results
