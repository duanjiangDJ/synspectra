from __future__ import annotations

import copy
import json
import os
from typing import Any

from .fields import ALL_OUTPUT_FIELDS, NEOSCA_OUTPUT_FIELDS, OTHER_OUTPUT_FIELDS, fields_for_methods


VALID_METHODS = ("custom", "leo", "quansyn", "neosca")


# Per-language model and parser settings. Keys are the values accepted by
# category_languages / --category-languages; "en" must keep the historical
# settings so existing English results stay comparable.
LANGUAGE_PROFILES: dict[str, dict[str, Any]] = {
    "en": {
        "stanza": {
            "language": "en",
            "processors": "tokenize,pos,lemma,depparse",
            "package": "default",
        },
        "leo": {"model_file": "english-ewt-ud-2.4-190531.udpipe"},
        "disabled_methods": [],
    },
    "zh": {
        # Chinese depparse requires the lemma processor, so the processor list
        # matches English; only the model packages differ.
        "stanza": {
            "language": "zh-hans",
            "processors": "tokenize,pos,lemma,depparse",
            "package": "default_fast",
        },
        "leo": {"model_file": "chinese-gsd-ud-2.4-190531.udpipe"},
        # NeoSCA/L2SCA measures are defined on English phrase structure.
        "disabled_methods": ["neosca"],
    },
}


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
    "language": "en",
    "category_languages": {},
    "language_profiles": LANGUAGE_PROFILES,
    "stanza": {
        "processors": "tokenize,pos,lemma,depparse",
        "use_gpu": False,
        "verbose": False,
        "download_method": "none",
        "workers": 4,
    },
    "leo": {
        "language_model_folder": "C:/",
    },
    "neosca": {
        "timeout": 1800,
        "batch_size": 2,
        "max_length": 300,
        "words_per_second": 15,
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


def resolve_language_profile(config: dict[str, Any], language: str) -> dict[str, Any]:
    """Returns the profile for a language, failing loudly on unknown names."""
    profiles = config.get("language_profiles") or LANGUAGE_PROFILES
    profile = profiles.get(language)
    if profile is None:
        known = ", ".join(sorted(profiles))
        raise ValueError(f"Unknown language '{language}' (known: {known})")
    return profile


def category_language(config: dict[str, Any], category_name: str) -> str:
    overrides = config.get("category_languages") or {}
    return overrides.get(category_name) or config.get("language", "en")


def set_methods(config: dict[str, Any], methods: set[str], output_fields: list[str] | None = None) -> None:
    config["methods"] = {method: method in methods for method in VALID_METHODS}
    config["output_fields"] = output_fields or fields_for_methods(
        config["methods"],
        include_all_quansyn=bool(config.get("include_all_quansyn_fields", False)),
    )


def apply_preset(config: dict[str, Any], preset: str) -> None:
    if preset == "all":
        set_methods(config, set(VALID_METHODS), ALL_OUTPUT_FIELDS)
        config["output_suffix"] = ""
    elif preset == "other":
        set_methods(config, {"custom", "leo", "quansyn"}, OTHER_OUTPUT_FIELDS)
        config["output_suffix"] = ""
    elif preset == "neosca":
        set_methods(config, {"neosca"}, NEOSCA_OUTPUT_FIELDS)
        config["output_suffix"] = "_NeoSCA"
