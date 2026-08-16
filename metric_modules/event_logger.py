from __future__ import annotations

import json
import sys
from typing import Any, TextIO

_mode = "text"
_stream: TextIO = sys.stdout
_task_id = ""


def configure(mode: str = "text", stream: TextIO | None = None) -> None:
    """Set output mode ("text" or "jsonl") and optionally redirect output."""
    global _mode, _stream
    if mode in ("text", "jsonl"):
        _mode = mode
    if stream is not None:
        _stream = stream


def set_task_id(task_id: str) -> None:
    global _task_id
    _task_id = task_id


def _write_json(event: dict[str, Any]) -> None:
    _stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    _stream.flush()


def human(message: str, end: str = "\n") -> None:
    """Write a line in human-readable mode; no-op in jsonl mode."""
    if _mode == "text":
        _stream.write(message)
        _stream.write(end)
        _stream.flush()


def log(level: str, message: str) -> None:
    if _mode == "jsonl":
        _write_json({"type": "log", "level": level, "message": message})
    else:
        human(message)


def stage(
    stage_name: str,
    message: str | None = None,
    human_message: str | None = None,
) -> None:
    text = human_message if human_message is not None else message
    if _mode == "jsonl":
        event: dict[str, Any] = {"type": "stage", "stage": stage_name}
        if message is not None:
            event["message"] = message
        _write_json(event)
    elif text is not None:
        human(text)


def progress(
    category: str,
    file: str,
    stage_name: str,
    done: int,
    total: int,
    human_message: str | None = None,
) -> None:
    if _mode == "jsonl":
        _write_json(
            {
                "type": "progress",
                "task_id": _task_id,
                "category": category,
                "file": file,
                "stage": stage_name,
                "done": done,
                "total": total,
            }
        )
    elif human_message is not None:
        human(human_message)


def task_start(
    task_id: str,
    preset: str | None = None,
    methods: list[str] | None = None,
) -> None:
    if _mode == "jsonl":
        event: dict[str, Any] = {"type": "task", "event": "start", "task_id": task_id}
        if preset is not None:
            event["preset"] = preset
        if methods is not None:
            event["methods"] = methods
        _write_json(event)


def task_end(
    task_id: str,
    status: str,
    output_files: list[str] | None = None,
) -> None:
    if _mode == "jsonl":
        event: dict[str, Any] = {
            "type": "task",
            "event": "end",
            "task_id": task_id,
            "status": status,
        }
        if output_files is not None:
            event["output_files"] = output_files
        _write_json(event)


def error(
    code: str,
    title: str,
    detail: str = "",
    suggestion: str | None = None,
) -> None:
    if _mode == "jsonl":
        event: dict[str, Any] = {
            "type": "error",
            "task_id": _task_id,
            "code": code,
            "title": title,
            "detail": detail,
        }
        if suggestion is not None:
            event["suggestion"] = suggestion
        _write_json(event)
    elif detail:
        human(f"{title}: {detail}")
    else:
        human(title)


def resource(
    resource_id: str,
    status: str,
    bytes_done: int | None = None,
    bytes_total: int | None = None,
    detail: str | None = None,
) -> None:
    if _mode == "jsonl":
        event: dict[str, Any] = {
            "type": "resource",
            "id": resource_id,
            "status": status,
        }
        if bytes_done is not None:
            event["bytes_done"] = bytes_done
        if bytes_total is not None:
            event["bytes_total"] = bytes_total
        if detail is not None:
            event["detail"] = detail
        _write_json(event)
    elif detail:
        human(detail)
