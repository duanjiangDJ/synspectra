from __future__ import annotations

import argparse
import os

from metric_modules.config import VALID_METHODS, apply_preset, load_config, set_methods
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
    parser.add_argument("--output-suffix", help="Override output_suffix from the config file.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing progress CSV files and rewrite outputs.")
    args = parser.parse_args()

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
    if args.output_suffix is not None:
        config["output_suffix"] = args.output_suffix
    if args.no_resume:
        config["resume"] = False

    run_pipeline(config, base_dir=base_dir)


if __name__ == "__main__":
    main()