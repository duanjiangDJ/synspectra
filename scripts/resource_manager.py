from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from metric_modules import event_logger  # noqa: E402

DEFAULT_MANIFEST = os.path.join(BASE_DIR, "resources", "resource_manifest.json")
STATE_FILE = "install_state.json"
ENV_FILE = "environment.json"

def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    is_64 = "64" in machine or machine in ("aarch64", "arm64")
    if system == "windows":
        return "windows-x64" if is_64 else "windows-x86"
    if system == "darwin":
        return "macos-arm64" if machine in ("aarch64", "arm64") else "macos-x64"
    return "linux-x64" if is_64 else "linux-x86"


def load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def load_state(data_dir: str) -> dict[str, dict[str, Any]]:
    state_path = os.path.join(data_dir, STATE_FILE)
    if not os.path.exists(state_path):
        return {}
    try:
        return load_json(state_path)
    except Exception:
        return {}


def save_state(data_dir: str, state: dict[str, dict[str, Any]]) -> None:
    write_json_atomic(os.path.join(data_dir, STATE_FILE), state)


def save_environment(data_dir: str, manifest: dict[str, Any]) -> None:
    state = load_state(data_dir)
    resources = manifest.get("resources", {})
    environment: dict[str, Any] = {
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "resources": {},
    }
    for resource_id, entry in state.items():
        if entry.get("status") != "ready":
            continue
        environment["resources"][resource_id] = {
            "version": entry.get("version")
            or resources.get(resource_id, {}).get("version"),
            "path": entry.get("path", ""),
            "status": "ready",
        }
    write_json_atomic(os.path.join(data_dir, ENV_FILE), environment)


def load_manifest(manifest_path: str) -> dict[str, Any]:
    return load_json(manifest_path)


def spec_for(resource_id: str, manifest: dict[str, Any], platform_name: str) -> dict[str, Any]:
    resources = manifest.get("resources", {})
    spec = resources.get(resource_id)
    if spec is None:
        raise KeyError(f"Unknown resource: {resource_id}")
    platforms = spec.get("platforms")
    if platforms is not None and platform_name not in platforms:
        raise ValueError(
            f"Resource {resource_id} does not support platform {platform_name}"
        )
    return spec


def _resolve_url(spec: dict[str, Any], platform_name: str) -> str:
    urls = spec.get("urls")
    if isinstance(urls, dict):
        url = urls.get(platform_name) or urls.get("all")
    elif isinstance(urls, list):
        url = urls[0] if urls else None
    else:
        url = urls
    if not url:
        raise ValueError(f"No download URL for platform {platform_name}")
    return url


def _resolve_hash(spec: dict[str, Any], platform_name: str) -> str:
    sha256 = spec.get("sha256")
    if isinstance(sha256, dict):
        sha256 = sha256.get(platform_name) or sha256.get("all", "")
    return str(sha256 or "")


def _resolve_size(spec: dict[str, Any], platform_name: str) -> int:
    size = spec.get("size", 0)
    if isinstance(size, dict):
        size = size.get(platform_name) or size.get("all", 0)
    return int(size or 0)


def _resolve_mirrors(spec: dict[str, Any], platform_name: str) -> list[str]:
    mirrors = spec.get("mirrors", [])
    if isinstance(mirrors, dict):
        mirrors = mirrors.get(platform_name) or mirrors.get("all", [])
    if not isinstance(mirrors, list):
        return []
    return [str(url) for url in mirrors]


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_disk_space(target_dir: str, needed_bytes: int) -> None:
    usage = shutil.disk_usage(target_dir)
    if usage.free < needed_bytes:
        raise OSError(
            f"Insufficient disk space: need {needed_bytes} bytes, "
            f"only {usage.free} bytes free"
        )


def download(
    url: str,
    dest: str,
    resource_id: str,
    expected_size: int,
    progress_interval: float = 0.05,
) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part_path = dest + ".part"
    existing = os.path.getsize(part_path) if os.path.exists(part_path) else 0
    headers = {"User-Agent": "SyntacticMetrics/0.1"}
    mode = "ab"
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
    else:
        mode = "wb"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        if existing > 0 and response.status != 206:
            existing = 0
            mode = "wb"
        total = expected_size or int(response.headers.get("Content-Length") or 0)
        last_report = 0.0
        with open(part_path, mode) as out:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                now = time.monotonic()
                if now - last_report >= progress_interval:
                    last_report = now
                    event_logger.resource(
                        resource_id,
                        "downloading",
                        bytes_done=existing + out.tell(),
                        bytes_total=total,
                    )
        done = existing + os.path.getsize(part_path) - existing
        event_logger.resource(
            resource_id,
            "downloading",
            bytes_done=done,
            bytes_total=total,
        )
    os.replace(part_path, dest)


def extract_zip_safe(archive_path: str, dest_dir: str) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        for info in zf.infolist():
            parts = PurePosixPath(info.filename.replace("\\", "/")).parts
            if (
                not parts
                or parts[0] in ("", "/")
                or ".." in parts
                or any(part.endswith(":") for part in parts)
            ):
                raise ValueError(f"Unsafe zip entry: {info.filename}")
            target = os.path.join(dest_dir, *parts)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def extract_tar_safe(archive_path: str, dest_dir: str) -> None:
    with tarfile.open(archive_path) as tf:
        for member in tf.getmembers():
            if member.issym() or member.islnk():
                raise ValueError(f"Unsafe tar link entry: {member.name}")
            parts = PurePosixPath(member.name.replace("\\", "/")).parts
            if (
                not parts
                or parts[0] in ("", "/")
                or ".." in parts
                or any(part.endswith(":") for part in parts)
            ):
                raise ValueError(f"Unsafe tar entry: {member.name}")
            target = os.path.join(dest_dir, *parts)
            if member.isdir():
                os.makedirs(target, exist_ok=True)
            elif member.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with tf.extractfile(member) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)


def extract_archive(archive_path: str, dest_dir: str) -> None:
    if archive_path.endswith(".zip"):
        extract_zip_safe(archive_path, dest_dir)
    elif archive_path.endswith((".tar", ".tar.gz", ".tgz")):
        extract_tar_safe(archive_path, dest_dir)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}")


def target_path(data_dir: str, spec: dict[str, Any]) -> str:
    return os.path.join(data_dir, spec["target"])


def mark_failure(
    data_dir: str,
    resource_id: str,
    version: str | None,
    status: str,
    detail: str,
) -> None:
    state = load_state(data_dir)
    state[resource_id] = {
        "status": status,
        "version": version,
        "detail": detail,
    }
    save_state(data_dir, state)
    event_logger.resource(resource_id, status, detail=detail)


def install_resource(
    resource_id: str,
    data_dir: str,
    manifest: dict[str, Any],
    platform_name: str,
    local_source: str | None = None,
) -> None:
    spec = spec_for(resource_id, manifest, platform_name)
    state = load_state(data_dir)
    current = state.get(resource_id, {})
    if current.get("status") == "ready" and current.get("version") == spec.get("version"):
        event_logger.log("info", f"Resource {resource_id} is already installed.")
        return

    kind = spec.get("kind")
    if kind == "stanza":
        _install_stanza_model(resource_id, data_dir, spec)
        return
    if kind not in ("file", "archive"):
        raise ValueError(f"Unsupported resource kind: {kind}")

    sha256 = _resolve_hash(spec, platform_name)
    if not sha256:
        raise ValueError(
            f"SHA-256 for {resource_id} is not pinned in the resource manifest; "
            "refusing to install for reproducibility."
        )
    expected_size = _resolve_size(spec, platform_name)
    target = target_path(data_dir, spec)

    state[resource_id] = {"status": "downloading", "version": spec.get("version")}
    save_state(data_dir, state)
    event_logger.resource(resource_id, "downloading", detail=f"Installing {resource_id}")

    if local_source:
        source_path = local_source
    else:
        try:
            urls = [_resolve_url(spec, platform_name)] + _resolve_mirrors(spec, platform_name)
            downloads_dir = os.path.join(data_dir, "downloads")
            check_disk_space(downloads_dir, expected_size * 2 + 1024 * 1024)
            source_path = os.path.join(
                downloads_dir,
                f"{resource_id}{_extension_from_url(urls[0])}",
            )
            last_error: Exception | None = None
            for url in urls:
                try:
                    download(url, source_path, resource_id, expected_size)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    event_logger.log("warning", f"Download failed for {url}: {exc}")
                    if os.path.exists(source_path + ".part"):
                        os.remove(source_path + ".part")
                    if os.path.exists(source_path):
                        os.remove(source_path)
            if last_error is not None:
                raise last_error
            if expected_size > 0 and os.path.getsize(source_path) != expected_size:
                raise RuntimeError(
                    f"Size mismatch for {resource_id}: expected {expected_size} bytes, "
                    f"got {os.path.getsize(source_path)} bytes"
                )
        except Exception as exc:
            mark_failure(
                data_dir,
                resource_id,
                spec.get("version"),
                "download_failed",
                str(exc),
            )
            raise

    event_logger.resource(resource_id, "verifying")
    actual_hash = sha256_file(source_path)
    if actual_hash != sha256:
        os.remove(source_path)
        detail = (
            f"SHA-256 mismatch for {resource_id}: expected {sha256}, "
            f"got {actual_hash}"
        )
        mark_failure(
            data_dir,
            resource_id,
            spec.get("version"),
            "download_failed",
            detail,
        )
        raise ValueError(detail)

    try:
        event_logger.resource(resource_id, "extracting" if kind == "archive" else "installing")
        if kind == "archive":
            tmp_dir = tempfile.mkdtemp(prefix=f"{resource_id}-", dir=os.path.join(data_dir, "downloads"))
            try:
                extract_archive(source_path, tmp_dir)
                children = os.listdir(tmp_dir)
                if len(children) == 1 and os.path.isdir(os.path.join(tmp_dir, children[0])):
                    inner = os.path.join(tmp_dir, children[0])
                    for name in os.listdir(inner):
                        os.replace(os.path.join(inner, name), os.path.join(tmp_dir, name))
                    os.rmdir(inner)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.exists(target):
                    shutil.rmtree(target)
                shutil.move(tmp_dir, target)
            finally:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source_path, target)
    except Exception as exc:
        mark_failure(
            data_dir,
            resource_id,
            spec.get("version"),
            "install_failed",
            str(exc),
        )
        raise

    if local_source is None:
        os.remove(source_path)
    state[resource_id] = {
        "status": "ready",
        "version": spec.get("version"),
        "path": target,
        "kind": kind,
    }
    save_state(data_dir, state)
    event_logger.resource(resource_id, "ready", detail=target)


def _install_stanza_model(resource_id: str, data_dir: str, spec: dict[str, Any]) -> None:
    try:
        import stanza  # type: ignore
    except ImportError:
        raise RuntimeError(
            "stanza is not installed; install the Python dependencies first."
        )
    if spec.get("resources_url"):
        os.environ["STANZA_RESOURCES_URL"] = str(spec["resources_url"])
    if spec.get("model_url"):
        os.environ["STANZA_MODEL_URL"] = str(spec["model_url"])
    state = load_state(data_dir)
    target = os.path.join(data_dir, spec.get("target", "stanza_resources"))
    state[resource_id] = {"status": "downloading", "version": spec.get("version", "latest")}
    save_state(data_dir, state)
    event_logger.resource(resource_id, "downloading", detail="Downloading Stanza model")
    try:
        stanza.download(
            "en",
            processors=spec.get("processors", "tokenize,pos,lemma,depparse"),
            model_dir=target,
            verbose=False,
        )
    except Exception as exc:
        mark_failure(
            data_dir,
            resource_id,
            spec.get("version", "latest"),
            "download_failed",
            str(exc),
        )
        raise
    state[resource_id] = {
        "status": "ready",
        "version": spec.get("version", "latest"),
        "path": target,
        "kind": "stanza",
    }
    save_state(data_dir, state)
    event_logger.resource(resource_id, "ready", detail=target)


def _extension_from_url(url: str) -> str:
    path = url.split("?", 1)[0].rstrip("/")
    for ext in (".zip", ".tar.gz", ".tgz", ".udpipe", ".tar"):
        if path.endswith(ext):
            return ext
    return ".bin"


def verify_resource(
    resource_id: str,
    data_dir: str,
    manifest: dict[str, Any],
    platform_name: str,
) -> bool:
    spec = spec_for(resource_id, manifest, platform_name)
    state = load_state(data_dir)
    entry = state.get(resource_id, {})
    if entry.get("status") != "ready":
        event_logger.log("warning", f"Resource {resource_id} is not installed.")
        return False
    target = entry.get("path") or target_path(data_dir, spec)
    if not os.path.exists(target):
        event_logger.log("warning", f"Resource {resource_id} is missing at {target}.")
        return False
    if spec.get("kind") == "file":
        sha256 = _resolve_hash(spec, platform_name)
        if sha256 and sha256_file(target) != sha256:
            event_logger.log("warning", f"Resource {resource_id} hash mismatch.")
            return False
    event_logger.log("info", f"Resource {resource_id} is ready.")
    return True


def uninstall_resource(resource_id: str, data_dir: str, manifest: dict[str, Any], platform_name: str) -> None:
    if resource_id == "python_runtime":
        state = load_state(data_dir)
        for name in ("venv", "runtime", "uv-cache"):
            target = os.path.join(data_dir, name)
            if os.path.exists(target):
                shutil.rmtree(target, ignore_errors=True)
        state.pop(resource_id, None)
        save_state(data_dir, state)
        event_logger.log("info", "Python runtime uninstalled.")
        return
    spec = spec_for(resource_id, manifest, platform_name)
    state = load_state(data_dir)
    entry = state.get(resource_id, {})
    target = entry.get("path") or target_path(data_dir, spec)
    if os.path.exists(target):
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
    state.pop(resource_id, None)
    save_state(data_dir, state)
    event_logger.log("info", f"Resource {resource_id} uninstalled.")


def dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def disk_usage(data_dir: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for name in ("runtime", "venv", "models", "stanza_resources", "java", "stanford", "downloads"):
        path = os.path.join(data_dir, name)
        if os.path.exists(path):
            result[name] = dir_size(path)
    return result


def offline_import(bundle_path: str, data_dir: str, manifest: dict[str, Any], platform_name: str) -> None:
    bundle_dir = tempfile.mkdtemp(prefix="offline-bundle-")
    try:
        extract_zip_safe(bundle_path, bundle_dir)
        offline_manifest_path = os.path.join(bundle_dir, "offline_manifest.json")
        if not os.path.exists(offline_manifest_path):
            raise ValueError("offline_manifest.json not found in bundle")
        offline_manifest = load_json(offline_manifest_path)
        if offline_manifest.get("platform") != platform_name:
            raise ValueError(
                f"Bundle platform {offline_manifest.get('platform')} does not match {platform_name}"
            )
        for resource_id in offline_manifest.get("resources", []):
            source = os.path.join(bundle_dir, "files", resource_id)
            if not os.path.exists(source):
                raise FileNotFoundError(f"Bundle is missing resource archive: {resource_id}")
            event_logger.log("info", f"Installing {resource_id} from offline bundle")
            install_resource(resource_id, data_dir, manifest, platform_name, local_source=source)
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)


def print_status(data_dir: str, manifest: dict[str, Any], platform_name: str) -> None:
    state = load_state(data_dir)
    resources = manifest.get("resources", {})
    for resource_id in sorted(resources):
        entry = state.get(resource_id, {})
        status = entry.get("status", "not_installed")
        version = entry.get("version", resources[resource_id].get("version", ""))
        event_logger.log(
            "info",
            f"{resource_id}\t{status}\t{version}\t{entry.get('path', '')}",
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage frontend runtime resources.")
    parser.add_argument("--data-dir", required=True, help="Application data directory.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to the resource manifest.")
    parser.add_argument("--platform", default=None, help="Override platform key (e.g. windows-x64).")
    parser.add_argument("--log-format", choices=("text", "jsonl"), default="text")
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="Install one resource or all resources.")
    p_install.add_argument("resource", nargs="?", default="all")

    p_verify = sub.add_parser("verify", help="Verify installed resources.")
    p_verify.add_argument("resource", nargs="?", default="all")

    p_uninstall = sub.add_parser("uninstall", help="Uninstall a resource.")
    p_uninstall.add_argument("resource")

    sub.add_parser("status", help="Show resource installation status.")
    sub.add_parser("disk-usage", help="Show disk usage of the data directory.")

    p_offline = sub.add_parser("offline-import", help="Install resources from an offline bundle.")
    p_offline.add_argument("bundle")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    event_logger.configure(args.log_format)
    platform_name = args.platform or platform_key()
    manifest = load_manifest(args.manifest)
    data_dir = args.data_dir
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(os.path.join(data_dir, "downloads"), exist_ok=True)

    try:
        if args.command == "install":
            resources = (
                [args.resource]
                if args.resource != "all"
                else sorted(manifest.get("resources", {}))
            )
            for resource_id in resources:
                try:
                    install_resource(resource_id, data_dir, manifest, platform_name)
                except Exception as exc:
                    state = load_state(data_dir)
                    if state.get(resource_id, {}).get("status") not in (
                        "download_failed",
                        "install_failed",
                    ):
                        state[resource_id] = {
                            "status": "install_failed",
                            "version": manifest.get("resources", {}).get(resource_id, {}).get("version"),
                            "detail": str(exc),
                        }
                        save_state(data_dir, state)
                    downloads_dir = os.path.join(data_dir, "downloads")
                    for name in os.listdir(downloads_dir):
                        if name.startswith(resource_id):
                            os.remove(os.path.join(downloads_dir, name))
                    raise
        elif args.command == "verify":
            resources = [args.resource] if args.resource != "all" else sorted(manifest.get("resources", {}))
            results = [verify_resource(rid, data_dir, manifest, platform_name) for rid in resources]
            if not all(results):
                return 1
        elif args.command == "uninstall":
            uninstall_resource(args.resource, data_dir, manifest, platform_name)
            save_environment(data_dir, manifest)
        elif args.command == "status":
            print_status(data_dir, manifest, platform_name)
        elif args.command == "disk-usage":
            for name, size in disk_usage(data_dir).items():
                event_logger.log("info", f"{name}\t{size}")
        elif args.command == "offline-import":
            offline_import(args.bundle, data_dir, manifest, platform_name)
            save_environment(data_dir, manifest)
        if args.command == "install":
            save_environment(data_dir, manifest)
        return 0
    except Exception as exc:
        event_logger.error(
            "RESOURCE_MANAGER_FAILED",
            str(exc),
            "",
            "Check the resource manifest and network connection.",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
