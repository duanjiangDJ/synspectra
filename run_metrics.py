from __future__ import annotations

import argparse
import os

from metric_modules.config import load_config
from metric_modules.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run configurable syntactic complexity metrics.")
    parser.add_argument("--config", default="metrics_config.json", help="Path to the JSON configuration file.")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config if os.path.isabs(args.config) else os.path.join(base_dir, args.config)
    run_pipeline(load_config(config_path), base_dir=base_dir)


if __name__ == "__main__":
    main()