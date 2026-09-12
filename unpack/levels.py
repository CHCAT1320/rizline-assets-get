import hashlib
import json
import os
from colorama import Fore
from unpack.paths import BUNDLES_DIR, DEFAULT_JSON, OUTPUT_DIR, ensure_dir
from unpack.unity import extract_typetrees, load_bundle, write_json


def parse_level():
    ensure_dir(OUTPUT_DIR)
    if not os.path.isdir(BUNDLES_DIR):
        print(Fore.RED + "未找到 bundle 目录")
        return

    candidates = []
    bundle_files = [
        filename
        for filename in os.listdir(BUNDLES_DIR)
        if filename.endswith(".bundle") and os.path.isfile(os.path.join(BUNDLES_DIR, filename))
    ]
    print(Fore.GREEN + f"扫描 {len(bundle_files)} 个 bundle 查找关卡信息", flush=True)
    for i, filename in enumerate(bundle_files, 1):
        path = os.path.join(BUNDLES_DIR, filename)
        env = load_bundle(filename)
        if env is None:
            continue
        for _name, tree in extract_typetrees(env, name="Default"):
            hash_text = hashlib.sha256(json.dumps(tree, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]
            out_name = f"default_{hash_text}.json"
            write_json(os.path.join(OUTPUT_DIR, out_name), tree)
            last_id = ""
            levels = tree.get("levels") or []
            if levels:
                last_id = levels[-1].get("id") or ""
            candidates.append(
                {
                    "file": out_name,
                    "data": tree,
                    "bundle": filename,
                    "mtime": os.path.getmtime(path),
                    "level_count": len(levels) + len(tree.get("discOLevels", [])),
                    "chart_count": len(tree.get("charts", [])),
                    "activity_time": tree.get("activityTime") or 0,
                    "last_id": last_id,
                    "is_temp": last_id.lower() == "temp",
                }
            )
        if i % 100 == 0 or i == len(bundle_files):
            print(Fore.CYAN + f"关卡扫描：{i}/{len(bundle_files)}", flush=True)

    if not candidates:
        print(Fore.RED + "未找到关卡信息文件")
        return

    newest = {}
    for item in candidates:
        current = newest.get(item["file"])
        if current is None or item["mtime"] > current["mtime"]:
            newest[item["file"]] = item
    file_infos = list(newest.values())
    file_infos.sort(
        key=lambda x: (x["mtime"], 0 if x["is_temp"] else 1, x["level_count"], x["chart_count"], x["activity_time"]),
        reverse=True,
    )

    print(Fore.GREEN + f"找到{len(file_infos)}个关卡信息文件（按来源 bundle 更新时间降序）：")
    for i, item in enumerate(file_infos):
        print(
            Fore.CYAN
            + f"{i + 1}. {item['file']}"
            + Fore.GREEN
            + f" 关卡{item['level_count']} 谱面{item['chart_count']} 末曲={item['last_id']} bundle={item['bundle']}"
        )
    selected = file_infos[0]
    print(
        Fore.GREEN
        + f"已自动选择最新关卡文件：{selected['file']}（关卡{selected['level_count']}，谱面{selected['chart_count']}，末曲={selected['last_id']}）"
    )
    write_json(DEFAULT_JSON, selected["data"])


def load_default():
    with open(DEFAULT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def all_levels(data=None):
    if data is None:
        data = load_default()
    return data.get("levels", []) + data.get("discOLevels", [])
