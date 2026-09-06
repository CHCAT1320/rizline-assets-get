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

    for filename in os.listdir(BUNDLES_DIR):
        env = load_bundle(filename)
        if env is None:
            continue
        for name, tree in extract_typetrees(env, name="Default"):
            hash_text = hashlib.sha256(json.dumps(tree, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]
            write_json(os.path.join(OUTPUT_DIR, f"default_{hash_text}.json"), tree)

    default_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("default_") and f.endswith(".json")]
    if not default_files:
        print(Fore.RED + "未找到关卡信息文件")
        return

    file_infos = []
    for filename in default_files:
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        level_count = len(data.get("levels", [])) + len(data.get("discOLevels", []))
        chart_count = len(data.get("charts", []))
        activity_time = data.get("activityTime") or 0
        mtime = os.path.getmtime(path)
        file_infos.append((filename, data, level_count, chart_count, activity_time, mtime))
    file_infos.sort(key=lambda x: (x[2], x[3], x[4], x[5]), reverse=True)

    print(Fore.GREEN + f"找到{len(file_infos)}个关卡信息文件（按最新降序）：")
    for i, (filename, _data, level_count, chart_count, activity_time, _mtime) in enumerate(file_infos):
        print(
            Fore.CYAN
            + f"{i + 1}. {filename}"
            + Fore.GREEN
            + f" 关卡{level_count} 谱面{chart_count} activityTime={activity_time}"
        )
    selected_file, data, level_count, chart_count, activity_time, _mtime = file_infos[0]
    print(
        Fore.GREEN
        + f"已自动选择最新关卡文件：{selected_file}（关卡{level_count}，谱面{chart_count}）"
    )
    write_json(DEFAULT_JSON, data)


def load_default():
    with open(DEFAULT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def all_levels(data=None):
    if data is None:
        data = load_default()
    return data.get("levels", []) + data.get("discOLevels", [])
