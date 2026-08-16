from __future__ import annotations

import argparse
import os
import sys
import uuid

from metric_modules.config import VALID_METHODS, apply_preset, load_config, set_methods
from metric_modules import event_logger
from metric_modules.pipeline import run_pipeline


def parse_methods(value: str) -> set[str]:
    methods = {method.strip().lower() for method in value.split(",") if method.strip()}
    invalid_methods = sorted(methods - set(VALID_METHODS))
    if invalid_methods:
        raise argparse.ArgumentTypeError(f"Unknown method(s): {', '.join(invalid_methods)}")
    if not methods:
        raise argparse.ArgumentTypeError("At least one method must be provided.")
    return methods


def main() -> None:
    parser = argparse.ArgumentParser(description="Run configurable syntactic complexity metrics.")
    parser.add_argument("--config", default="metrics_config.json", help="Path to the JSON configuration file.")
    parser.add_argument(
        "--preset",
        choices=("all", "other", "neosca"),
        help="Use a built-in method preset instead of the methods in the config file.",
    )
    parser.add_argument(
        "--methods",
        type=parse_methods,
        help="Comma-separated methods to enable, e.g. custom,leo,quansyn or neosca.",
    )
    parser.add_argument("--source-dir", help="Override source_dir from the config file.")
    parser.add_argument("--result-dir", help="Override result_dir from the config file.")
    parser.add_argument("--leo-model-folder", help="Override leo.language_model_folder from the config file.")
    parser.add_argument("--output-suffix", help="Override output_suffix from the config file.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing progress CSV files and rewrite outputs.")
    parser.add_argument(
        "--log-format",
        choices=("text", "jsonl"),
        default="text",
        help="Output format: human-readable text (default) or JSON Lines events.",
    )
    parser.add_argument(
        "--log-file",
        help="Write logs to this file instead of stdout.",
    )
    args = parser.parse_args()

    log_stream = None
    if args.log_file:
        log_stream = open(args.log_file, "w", encoding="utf-8")
    event_logger.configure(args.log_format, stream=log_stream)
    task_id = uuid.uuid4().hex
    event_logger.set_task_id(task_id)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config if os.path.isabs(args.config) else os.path.join(base_dir, args.config)
    config = load_config(config_path)

    if args.preset:
        apply_preset(config, args.preset)
    if args.methods:
        set_methods(config, args.methods)
    if args.source_dir:
        config["source_dir"] = args.source_dir
    if args.result_dir:
        config["result_dir"] = args.result_dir
    if args.leo_model_folder:
        config.setdefault("leo", {})["language_model_folder"] = args.leo_model_folder
    if args.output_suffix is not None:
        config["output_suffix"] = args.output_suffix
    if args.no_resume:
        config["resume"] = False

    methods = [name for name, enabled in config.get("methods", {}).items() if enabled]
    event_logger.task_start(task_id, preset=args.preset, methods=methods)
    try:
        output_files = run_pipeline(config, base_dir=base_dir)
    except Exception as exc:
        event_logger.task_end(task_id, "error")
        event_logger.error(
            "PIPELINE_FAILED",
            "Pipeline run failed",
            str(exc),
            "Check the logs above for details.",
        )
        if log_stream is not None:
            log_stream.close()
        sys.exit(1)

    event_logger.task_end(task_id, "success", output_files=output_files)
    if log_stream is not None:
        log_stream.close()


if __name__ == "__main__":
    main()
