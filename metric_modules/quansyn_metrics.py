from __future__ import annotations

from quansyn.depval import DepValAnalyzer

from . import event_logger


QUANSYN_METRICS = ["mhd", "tdl", "sl", "mv", "vk", "hi", "hf", "mtw", "mth", "mtdl", "msl", "mdd", "ndd"]
QUANSYN_RENAME_MAP = {
    "mhd": "MHD",
    "tdl": "TDL",
    "sl": "SL",
    "mv": "MV",
    "vk": "VK",
    "hi": "HI",
    "hf": "HF",
    "mtdl": "MTDL",
    "msl": "MSL",
    "mtw": "MTW",
    "mth": "MTH",
    "mdd": "MDD_quansyn",
    "ndd": "NDD_quansyn",
}


def compute_quansyn_text_metrics(conllu_str: str) -> dict[str, float | str]:
    try:
        analyzer = DepValAnalyzer(conllu_str)
        text_metrics = analyzer.calculate_text_metrics(metrics=QUANSYN_METRICS)
    except Exception as exc:
        event_logger.error(
            "QUANSYN_CALC_FAILED",
            "QuanSyn calculation failed",
            str(exc),
            "Check the CoNLL-U input from Stanza.",
        )
        return {}

    result: dict[str, float | str] = {}
    for raw_key, friendly_key in QUANSYN_RENAME_MAP.items():
        if raw_key in text_metrics:
            value = text_metrics[raw_key]
            if isinstance(value, (int, float)):
                result[friendly_key] = round(float(value), 4)
            else:
                result[friendly_key] = value
    return result
