from __future__ import annotations

import copy
import json
import os
from typing import Any

from .fields import OTHER_OUTPUT_FIELDS


DEFAULT_CONFIG: dict[str, Any] = {
    "source_dir": "source",
    "result_dir": "result",
    "resume": True,
    "cleanup_leo_results": True,
    "output_suffix": "",
    "methods": {
        "custom": True,
        "leo": True,
        "quansyn": True,
        "neosca": False,
    },
    "output_fields": OTHER_OUTPUT_FIELDS,
    "stanza": {
        "processors": "tokenize,pos,lemma,depparse",
        "use_gpu": False,
        "verbose": False,
    },
    "leo": {
        "language_model_folder": "C:/",
    },
    "neosca": {
        "timeout": 1000,
    },
}


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | None = "metrics_config.json") -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    if not config_path or not os.path.exists(config_path):
        return config

    with open(config_path, "r", encoding="utf-8") as f:
        user_config = json.load(f)
    return deep_merge(config, user_config)