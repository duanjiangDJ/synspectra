from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from . import event_logger


def _parse_row(row: dict[str, str]) -> dict[str, float | str]:
    result: dict[str, float | str] = {}
    for key, value in row.items():
        if key == "Filename":
            continue
        try:
            result[key] = round(float(value), 4)
        except (ValueError, TypeError):
            result[key] = value
    return result


class NeoSCABatcher:
    """
    Batches many files into single NeoSCA (JVM) invocations.

    Starting one JVM per file dominates NeoSCA runtime; the CLI accepts
    multiple input files per call, so a batch of N files pays the JVM +
    Stanford Parser startup cost once instead of N times.
    """

    def __init__(
        self,
        timeout: int = 300,
        batch_size: int = 10,
        max_length: int | None = None,
    ) -> None:
        self.timeout = timeout
        self.batch_size = max(1, batch_size)
        self.max_length = max_length
        self._pending: list[tuple[str, str]] = []
        self._results: dict[str, dict[str, float | str]] = {}

    def submit(self, filename: str, text_content: str) -> bool:
        """Queues one file; returns True when a batch was executed."""
        if not text_content.strip():
            self._results[filename] = {}
            return False
        self._pending.append((filename, text_content))
        if len(self._pending) >= self.batch_size:
            self._run()
            return True
        return False

    def take(self, filename: str) -> dict[str, float | str]:
        return self._results.pop(filename, {})

    def flush(self) -> None:
        self._run()

    def _run(self) -> None:
        if not self._pending:
            return
        batch = self._pending
        self._pending = []

        tmp_dir = tempfile.mkdtemp()
        csv_path = os.path.join(tmp_dir, "result.csv")
        try:
            input_paths: list[str] = []
            for filename, text_content in batch:
                txt_path = os.path.join(tmp_dir, filename)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(text_content)
                input_paths.append(txt_path)

            args = [sys.executable, "-m", "neosca", *input_paths, "-o", csv_path]
            if self.max_length is not None:
                args += ["--max-length", str(self.max_length)]

            subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )

            if not os.path.exists(csv_path):
                event_logger.error(
                    "NEOSCA_NO_RESULT",
                    "NeoSCA did not generate a result file.",
                    csv_path,
                    "Check NeoSCA/Java installation and rerun.",
                )
                for filename, _ in batch:
                    self._results[filename] = {}
                return

            with open(csv_path, "r", encoding="utf-8") as f:
                # NeoSCA writes the full input path in "Filename" when given
                # absolute paths, and the basename when given relative ones.
                rows_by_file = {
                    os.path.basename(row["Filename"]): row for row in csv.DictReader(f)
                }
            for filename, _ in batch:
                row = rows_by_file.get(filename)
                self._results[filename] = _parse_row(row) if row else {}

        except subprocess.TimeoutExpired:
            event_logger.error(
                "NEOSCA_TIMEOUT",
                "NeoSCA batch timed out.",
                f"Timeout after {self.timeout} seconds for {len(batch)} files.",
                "Increase neosca.timeout or reduce neosca.batch_size.",
            )
            for filename, _ in batch:
                self._results[filename] = {}
        except subprocess.CalledProcessError as exc:
            event_logger.error(
                "NEOSCA_CALL_FAILED",
                "NeoSCA batch failed",
                str(exc.stderr)[-2000:],
                "Check the NeoSCA environment resources.",
            )
            for filename, _ in batch:
                self._results[filename] = {}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def compute_neosca_metrics(text_content: str, timeout: int = 300) -> dict[str, float | str]:
    """Single-file convenience wrapper (kept for backward compatibility)."""
    batcher = NeoSCABatcher(timeout=timeout, batch_size=1)
    batcher.submit("sample.txt", text_content)
    batcher.flush()
    return batcher.take("sample.txt")
