from __future__ import annotations

import os

from metric_modules.config import load_config
from metric_modules.fields import ALL_OUTPUT_FIELDS
from metric_modules.pipeline import run_pipeline


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config = load_config(os.path.join(base_dir, "metrics_config.json"))
    config["methods"] = {"custom": True, "leo": True, "quansyn": True, "neosca": True}
    config["output_fields"] = ALL_OUTPUT_FIELDS
    config["output_suffix"] = ""
    run_pipeline(config, base_dir=base_dir)


if __name__ == "__main__":
    main()