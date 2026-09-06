import json
import os
from unpack.parser import parse_unity_catalog
from unpack.paths import CATALOG_PATH, FILELIST_PATH, ensure_dir


def parse_catalog() -> list:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    key_data = parse_unity_catalog(catalog)
    ensure_dir(os.path.dirname(FILELIST_PATH))
    with open(FILELIST_PATH, "w", encoding="utf-8") as f:
        json.dump(key_data, f, indent=4, ensure_ascii=False, separators=(",", ": "))
    return key_data


def load_file_list() -> list:
    with open(FILELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_bundle_map(file_list=None) -> dict:
    if file_list is None:
        file_list = load_file_list()
    mapping = {}
    for item in file_list:
        if len(item) < 2:
            continue
        key, value = item[0], item[1]
        if isinstance(key, str) and isinstance(value, str) and value.endswith(".bundle"):
            mapping[key] = value
    return mapping
