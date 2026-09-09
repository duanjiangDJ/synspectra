CUSTOM_FIELDS = ["MHDD", "AlphaDepLength", "MDD", "NDD"]
LEO_FIELDS = ["MDD_Leo", "NDD_Leo"]
QUANSYN_FIELDS = [
    "MDD_quansyn", "NDD_quansyn",
    "MHD", "MV", "VK", "MTW", "MTH", "HI", "HF", "MTDL", "MSL",
]
QUANSYN_ALL_FIELDS = [
    "MDD_quansyn", "NDD_quansyn",
    "MHD", "TDL", "SL", "MV", "VK", "MTW", "MTH", "HI", "HF", "MTDL", "MSL",
]
NEOSCA_FIELDS = [
    "MLS", "MLT", "MLC", "C/S", "VP/T", "C/T", "DC/C", "DC/T",
    "T/S", "CT/T", "CP/T", "CP/C", "CN/T", "CN/C",
    "W", "S", "VP", "C", "T", "DC", "CT", "CP", "CN",
]

OTHER_OUTPUT_FIELDS = ["filename"] + CUSTOM_FIELDS + LEO_FIELDS + QUANSYN_FIELDS
ALL_OUTPUT_FIELDS = ["filename"] + CUSTOM_FIELDS + LEO_FIELDS + QUANSYN_ALL_FIELDS + NEOSCA_FIELDS
NEOSCA_OUTPUT_FIELDS = ["filename"] + NEOSCA_FIELDS


def fields_for_methods(methods: dict[str, bool], include_all_quansyn: bool = False) -> list[str]:
    fields = ["filename"]
    if methods.get("custom", False):
        fields.extend(CUSTOM_FIELDS)
    if methods.get("leo", False):
        fields.extend(LEO_FIELDS)
    if methods.get("quansyn", False):
        fields.extend(QUANSYN_ALL_FIELDS if include_all_quansyn else QUANSYN_FIELDS)
    if methods.get("neosca", False):
        fields.extend(NEOSCA_FIELDS)
    return fields


_METHOD_FIELD_GROUPS: dict[str, list[str]] = {
    "custom": CUSTOM_FIELDS,
    "leo": LEO_FIELDS,
    "quansyn": QUANSYN_ALL_FIELDS,
    "neosca": NEOSCA_FIELDS,
}


def filter_fields_for_methods(fields: list[str], methods: dict[str, bool]) -> list[str]:
    """Drops columns that belong only to methods disabled for a category.

    A category can run with fewer methods than the global configuration (for
    example NeoSCA has no Chinese model), and the CSV header must then match
    what was actually computed.
    """
    disabled: set[str] = set()
    for method, group in _METHOD_FIELD_GROUPS.items():
        if not methods.get(method, False):
            disabled.update(group)
    return [field for field in fields if field == "filename" or field not in disabled]