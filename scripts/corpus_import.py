from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from resource_manager import extract_zip_safe  # noqa: E402


def emit(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def collect_groups(root: str) -> list[dict]:
    groups: list[dict] = []

    def walk(path: str, rel: str, depth: int) -> None:
        if depth > 10:
            return
        txt_files: list[str] = []
        subdirs: list[str] = []
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            return
        for name in entries:
            if name.startswith(".") or name.endswith("_results_dd"):
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                subdirs.append(full)
            elif name.lower().endswith(".txt"):
                txt_files.append(full)
        if txt_files:
            top_name = rel.split("/")[0] if rel else os.path.basename(root.rstrip("/\\"))
            groups.append(
                {
                    "path": rel,
                    "name": top_name or os.path.basename(path.rstrip("/\\")) or "corpus",
                    "file_count": len(txt_files),
                    "files": sorted(txt_files),
                }
            )
        for subdir in subdirs:
            child = os.path.basename(subdir)
            next_rel = child if not rel else f"{rel}/{child}"
            walk(subdir, next_rel, depth + 1)

    walk(root, "", 0)
    groups.sort(key=lambda group: group["path"])
    return groups


def prepare_input(input_path: str) -> tuple[str, str | None]:
    if zipfile.is_zipfile(input_path):
        tmp_dir = tempfile.mkdtemp(prefix="corpus-zip-")
        extract_zip_safe(input_path, tmp_dir)
        return tmp_dir, tmp_dir
    return input_path, None


def unique_destination(directory: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    index = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base}_{index}{ext}")
        index += 1
    return candidate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan and import corpus text files.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan a zip or directory and report text groups.")
    p_scan.add_argument("input")

    p_import = sub.add_parser("import", help="Import text groups into the source directory.")
    p_import.add_argument("input")
    p_import.add_argument("--source-dir", required=True)
    p_import.add_argument(
        "--conflict",
        choices=("skip", "overwrite"),
        default="skip",
    )

    p_rename = sub.add_parser(
        "rename-category",
        help="Rename a category folder in the source directory.",
    )
    p_rename.add_argument("--source-dir", required=True)
    p_rename.add_argument("--old", required=True)
    p_rename.add_argument("--new", required=True)

    p_delete = sub.add_parser(
        "delete-category",
        help="Delete a category folder in the source directory.",
    )
    p_delete.add_argument("--source-dir", required=True)
    p_delete.add_argument("--name", required=True)

    args = parser.parse_args(argv)
    root = None
    tmp_dir = None
    if args.command in ("scan", "import"):
        root, tmp_dir = prepare_input(args.input)
    try:
        if args.command in ("scan", "import"):
            groups = collect_groups(root)
            emit(
                {
                    "type": "corpus",
                    "event": "scan",
                    "input": args.input,
                    "groups": [
                        {
                            "path": group["path"],
                            "name": group["name"],
                            "file_count": group["file_count"],
                        }
                        for group in groups
                    ],
                }
            )
        if args.command == "import":
            source_dir = os.path.abspath(args.source_dir)
            os.makedirs(source_dir, exist_ok=True)
            imported = 0
            skipped = 0
            total = sum(group["file_count"] for group in groups)
            for group in groups:
                category = group["name"].replace("/", "_").replace("\\", "_")
                target_dir = os.path.join(source_dir, category)
                os.makedirs(target_dir, exist_ok=True)
                for source_file in group["files"]:
                    filename = os.path.basename(source_file)
                    destination = os.path.join(target_dir, filename)
                    if os.path.exists(destination):
                        if args.conflict == "skip":
                            skipped += 1
                            continue
                    shutil.copy2(source_file, destination)
                    imported += 1
                    emit(
                        {
                            "type": "corpus",
                            "event": "progress",
                            "done": imported,
                            "total": total,
                        }
                    )
            emit(
                {
                    "type": "corpus",
                    "event": "done",
                    "imported": imported,
                    "skipped": skipped,
                    "source_dir": source_dir,
                }
            )
        elif args.command == "rename-category":
            source_dir = os.path.abspath(args.source_dir)
            for name in (args.old, args.new):
                if name in ("", ".", "..") or "/" in name or "\\" in name:
                    raise ValueError(f"Invalid category name: {name}")
            old_path = os.path.join(source_dir, args.old)
            new_path = os.path.join(source_dir, args.new)
            if not os.path.isdir(old_path):
                raise FileNotFoundError(f"Category not found: {args.old}")
            if os.path.exists(new_path):
                raise FileExistsError(f"Category already exists: {args.new}")
            os.rename(old_path, new_path)
            emit(
                {
                    "type": "corpus",
                    "event": "renamed",
                    "old": args.old,
                    "new": args.new,
                }
            )
        elif args.command == "delete-category":
            source_dir = os.path.abspath(args.source_dir)
            if args.name in ("", ".", "..") or "/" in args.name or "\\" in args.name:
                raise ValueError(f"Invalid category name: {args.name}")
            target = os.path.join(source_dir, args.name)
            if not os.path.isdir(target):
                raise FileNotFoundError(f"Category not found: {args.name}")
            shutil.rmtree(target)
            emit(
                {
                    "type": "corpus",
                    "event": "deleted",
                    "name": args.name,
                }
            )
        return 0
    except Exception as exc:
        emit(
            {
                "type": "corpus",
                "event": "error",
                "detail": str(exc),
            }
        )
        return 1
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
