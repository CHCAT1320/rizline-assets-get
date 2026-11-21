import os
from unpack.audio import convert_acb_to_wav, find_acb, list_acb_files
from unpack.classify import classify_key
from unpack.paths import BUNDLES_DIR, CATALOG_PATH, CHARTS_DIR, OUTPUT_DIR, ensure_dir, safe_filename
from unpack.unity import (
    extract_fonts,
    extract_images,
    extract_text_assets,
    extract_typetrees,
    extract_video_clips,
    load_bundle,
    write_bytes,
    write_json,
)


def export_text_json(env, dest_path):
    items = extract_text_assets(env)
    if not items:
        return 0
    write_bytes(dest_path, items[0][1])
    return 1


def export_images(env, dest_path):
    items = extract_images(env)
    if not items:
        return 0
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    items[0][1].save(dest_path)
    return 1


def export_localization(env, dest_path):
    items = extract_text_assets(env)
    if not items:
        return 0
    write_bytes(dest_path, items[0][1])
    return 1


def export_banner_config(env, dest_path):
    items = extract_typetrees(env)
    if not items:
        return 0
    write_json(dest_path, items[0][1])
    return 1


def export_video(env, dest_dir):
    items = extract_video_clips(env)
    count = 0
    for name, blob in items:
        write_bytes(os.path.join(dest_dir, safe_filename(name)), blob)
        count += 1
    return count


def export_ui_asset(env, dest_path):
    ext = os.path.splitext(dest_path)[1].lower()
    if ext in {".png", ".jpg", ".jpeg"}:
        return export_images(env, dest_path)
    if ext in {".json", ".txt", ".lua"}:
        items = extract_text_assets(env)
        if items:
            write_bytes(dest_path, items[0][1])
            return 1
        return 0
    if ext == ".ttf":
        from unpack.unity import extract_fonts

        fonts = extract_fonts(env)
        if fonts:
            write_bytes(dest_path, fonts[0][1])
            return 1
        return 0
    images = extract_images(env)
    if images:
        path = dest_path if ext else dest_path + ".png"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        images[0][1].save(path)
        return 1
    texts = extract_text_assets(env)
    if texts:
        write_bytes(dest_path if ext else dest_path + ".txt", texts[0][1])
        return 1
    trees = extract_typetrees(env)
    if trees:
        write_json(dest_path if ext else dest_path + ".json", trees[0][1])
        return 1
    return 0


TYPE_EXPORTERS = {
    "chart": export_text_json,
    "illustration": export_images,
    "alt_illustration": export_images,
    "layout": export_images,
    "series_banner": export_images,
    "series_poster": export_images,
    "avatar": export_images,
    "sticker": export_images,
    "banner": export_images,
    "banner_config": export_banner_config,
    "localization": export_localization,
}


def export_catalog_asset(key, bundle_name):
    kind, relpath = classify_key(key)
    if kind == "skip" or relpath is None:
        return kind, 0
    dest = os.path.join(OUTPUT_DIR, relpath)
    try:
        env = load_bundle(bundle_name)
        if env is None:
            return kind, 0
        if kind == "video":
            count = export_video(env, dest)
        elif kind == "ui_asset":
            count = export_ui_asset(env, dest)
        else:
            exporter = TYPE_EXPORTERS.get(kind)
            count = exporter(env, dest) if exporter is not None else 0
        if count:
            return kind, count
        # 兜底：按类型导出失败（例如 banner.* 实际是 UI 预制体而非图片），
        # 改为导出 bundle 内的原始内容（MonoBehaviour JSON / TextAsset 等），避免静默遗漏。
        fallback_dir = os.path.join(OUTPUT_DIR, "bundles_misc", safe_filename(key))
        return kind, export_bundle_contents(bundle_name, fallback_dir)
    except Exception:
        return kind, 0


def export_level_pack(level, data, bundle_map, extra_chart_ids=None):
    level_id = level["id"]
    name = level_id.split(".")[0]
    disc_name = level["discName"]
    chart_ids = list(level.get("chartIds", []))
    if extra_chart_ids:
        for extra in extra_chart_ids:
            if extra not in chart_ids:
                chart_ids.append(extra)
    illustration_id = level["illustrationId"]
    music_id = level["musicId"]
    out_dir = ensure_dir(os.path.join(CHARTS_DIR, disc_name, name))

    exported_charts = 0
    for chart_id in chart_ids:
        dest = os.path.join(out_dir, f"{chart_id}.json")
        bundle_name = bundle_map.get(chart_id)
        if not bundle_name:
            continue
        env = load_bundle(bundle_name)
        if env is None:
            continue
        exported_charts += export_text_json(env, dest)

    for image_id in _level_image_ids(level, bundle_map):
        dest = os.path.join(out_dir, f"{image_id}.png")
        bundle_name = bundle_map.get(image_id)
        if not bundle_name:
            continue
        env = load_bundle(bundle_name)
        if env is None:
            continue
        export_images(env, dest)

    acb_path = find_acb(name)
    wav_path = os.path.join(out_dir, f"{music_id}.wav")
    wav_ok = False
    if acb_path:
        wav_ok = convert_acb_to_wav(acb_path, wav_path)

    chart_level = []
    for chart in data.get("charts", []):
        if chart["id"] in chart_ids:
            chart_level.append(
                {
                    "difficultyLevel": chart["level"],
                    "difficulty": chart["difficulty"],
                    "designer": chart["designer"],
                }
            )
    chart_info = {
        "name": name,
        "levelId": level_id,
        "discName": disc_name,
        "chartIds": chart_ids,
        "illustrationId": illustration_id,
        "musicId": music_id,
        "appearType": level.get("appearType"),
        "seriesIndex": level.get("seriesIndex"),
        "isNewLevel": level.get("isNewLevel"),
        "chartLevel": chart_level,
        "extraChartIds": extra_chart_ids or [],
    }
    write_json(os.path.join(out_dir, "chartInfo.json"), chart_info)
    return {
        "name": name,
        "disc": disc_name,
        "charts": exported_charts,
        "wav": wav_ok,
    }


def _level_image_ids(level, bundle_map):
    ids = [level["illustrationId"]]
    base = level["illustrationId"]
    for suffix in (".HiRes", ".cn", ".cn.HiRes"):
        candidate = base + suffix
        if candidate in bundle_map:
            ids.append(candidate)
    return ids


def extra_charts_for_level(level, bundle_map):
    extras = []
    prefix = f"chart.{level['id']}."
    official = set(level.get("chartIds", []))
    for key in bundle_map:
        if key in official:
            continue
        if key.startswith(prefix):
            extras.append(key)
    extras.sort()
    return extras


def _unique_filename(used, base, ext):
    base = base or "unnamed"
    candidate = base + ext
    i = 1
    while candidate in used:
        i += 1
        candidate = f"{base}_{i}{ext}"
    used.add(candidate)
    return candidate


def export_bundle_contents(bundle_name, dest_dir):
    try:
        env = load_bundle(bundle_name)
        if env is None:
            return 0
        count = 0
        used = set()
        ensure_dir(dest_dir)
        for name, image in extract_images(env):
            path = os.path.join(dest_dir, _unique_filename(used, safe_filename(name), ".png"))
            image.save(path)
            count += 1
        for name, raw in extract_text_assets(env):
            ext = ".json" if raw.lstrip().startswith(b"{") or raw.lstrip().startswith(b"[") else ".txt"
            path = os.path.join(dest_dir, _unique_filename(used, safe_filename(name), ext))
            write_bytes(path, raw)
            count += 1
        for name, tree in extract_typetrees(env):
            path = os.path.join(dest_dir, _unique_filename(used, safe_filename(name or "MonoBehaviour"), ".json"))
            write_json(path, tree)
            count += 1
        for name, blob in extract_fonts(env):
            path = os.path.join(dest_dir, _unique_filename(used, safe_filename(name), ".ttf"))
            write_bytes(path, blob)
            count += 1
        for name, blob in extract_video_clips(env):
            path = os.path.join(dest_dir, _unique_filename(used, safe_filename(name), ""))
            write_bytes(path, blob)
            count += 1
        return count
    except Exception:
        return 0


def export_remaining_bundles(used_bundles):
    if not os.path.isdir(BUNDLES_DIR):
        return 0, 0
    used = {os.path.basename(name) for name in used_bundles if name}
    leftover_dir = ensure_dir(os.path.join(OUTPUT_DIR, "bundles_misc"))
    exported = 0
    empty = 0
    for filename in os.listdir(BUNDLES_DIR):
        path = os.path.join(BUNDLES_DIR, filename)
        if not filename.endswith(".bundle") or filename in used or not os.path.isfile(path):
            continue
        dest = os.path.join(leftover_dir, filename.replace(".bundle", ""))
        count = export_bundle_contents(filename, dest)
        if count:
            exported += 1
        else:
            empty += 1
    return exported, empty


def export_remaining_audio(used_acb_names):
    from colorama import Fore

    audio_dir = ensure_dir(os.path.join(OUTPUT_DIR, "audio"))
    used = {os.path.basename(name).lower() for name in used_acb_names if name}
    files = [path for path in list_acb_files() if os.path.basename(path).lower() not in used]
    converted = 0
    failed = 0
    total = len(files)
    for i, acb_path in enumerate(files, 1):
        filename = os.path.basename(acb_path)
        wav_path = os.path.join(audio_dir, os.path.splitext(filename)[0] + ".wav")
        if convert_acb_to_wav(acb_path, wav_path):
            converted += 1
        else:
            failed += 1
        if i % 10 == 0 or i == total:
            print(Fore.CYAN + f"音频转换：{i}/{total}", flush=True)
    return converted, failed


def _is_alias_key(key):
    """fileList 中指向 bundle 的别名键（bundle 名或 32 位 hex），不算资源遗漏。"""
    return key.endswith(".bundle") or (len(key) == 32 and all(c in "0123456789abcdef" for c in key))


def _is_intentional_skip(key):
    """classify_key 中明确不需要导出的资源（材质/预制体）。"""
    if key.startswith("Assets/Rizline/") or key.startswith("Assets/Le Tai"):
        return key.lower().endswith((".mat", ".prefab"))
    return False


def _is_known_audio_key(key):
    """CRI 音频 addressable 键，音频由 acb 目录按文件名单独处理，不算遗漏。"""
    return key.startswith("CriAddressables/")


def _catalog_bundle_names():
    """catalog m_InternalIds 中出现的 bundle 文件名集合。"""
    try:
        import json

        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    except Exception:
        return set()
    names = set()
    for item in catalog.get("m_InternalIds", []):
        if isinstance(item, str) and item.startswith("http"):
            names.add(item.rsplit("/", 1)[-1])
    return names


def _chart_owner_level(key, level_ids):
    if key.startswith("chart.challenge."):
        return "__challenge__"
    for lid in level_ids:
        if key.startswith(f"chart.{lid}."):
            return lid
    return None


def audit_resources(data, bundle_map, used_acb_names, assigned_charts, export_results, levels):
    """
    导出后完整性检查：找出可能被遗漏的资源并生成报告。
    - 存在于 catalog 但不在任何关卡 chartIds 中的隐藏谱面（如隐藏 EZ）
    - 未关联到任何关卡的孤儿谱面
    - 分类后导出失败（导出了 0 个对象）的资源
    - 被归为 skip 但并非 bundle 别名/有意忽略的未知资源类型
    - 磁盘上存在但未被 fileList 引用的 bundle（残留/热更包）
    - 存在但未被任何关卡使用的 acb 音频
    """
    from colorama import Fore

    issues = {}
    level_ids = [lv["id"] for lv in levels]
    level_chart_ids = {lv["id"]: set(lv.get("chartIds", [])) for lv in levels}

    # 0) 隐藏谱面：属于某关卡前缀，但不在该关卡 chartIds 里
    hidden_charts = []
    orphan_charts = []
    for key in bundle_map:
        if not key.startswith("chart."):
            continue
        owner = _chart_owner_level(key, level_ids)
        if owner is None:
            orphan_charts.append(key)
            continue
        if owner == "__challenge__":
            continue
        if key not in level_chart_ids.get(owner, set()):
            hidden_charts.append(
                {"key": key, "level": owner, "exported": key in assigned_charts}
            )
    hidden_charts.sort(key=lambda x: x["key"])
    orphan_charts.sort()
    if hidden_charts:
        issues["hidden_charts"] = hidden_charts
    if orphan_charts:
        issues["orphan_charts"] = orphan_charts

    # 1) 分类导出失败（有资源但导出 0 个对象）
    failed_exports = sorted(
        [{"key": key, "kind": kind} for key, kind, count in export_results if count == 0],
        key=lambda x: x["key"],
    )
    if failed_exports:
        issues["failed_exports"] = failed_exports

    # 2) 未知类型（被 skip 丢掉的资源）
    unknown_keys = sorted(
        key for key in bundle_map
        if classify_key(key)[0] == "skip"
        and not _is_alias_key(key)
        and not _is_intentional_skip(key)
        and not _is_known_audio_key(key)
    )
    if unknown_keys:
        issues["unknown_keys"] = unknown_keys

    # 3) 磁盘上存在、但未被 fileList 或 catalog 引用的 bundle（可能来自热更，建议确认）
    used_bundles = {
        os.path.basename(name)
        for name in bundle_map.values()
        if isinstance(name, str) and name.endswith(".bundle")
    }
    catalog_bundles = _catalog_bundle_names()
    if os.path.isdir(BUNDLES_DIR):
        on_disk = {f for f in os.listdir(BUNDLES_DIR) if f.endswith(".bundle")}
    else:
        on_disk = set()
    unreferenced_bundles = sorted(on_disk - used_bundles - catalog_bundles)
    if unreferenced_bundles:
        issues["unreferenced_bundles"] = unreferenced_bundles

    # 4) 未被关卡使用的 acb 音频
    used_acb = {os.path.basename(n).lower() for n in used_acb_names if n}
    all_acb = sorted(os.path.basename(p) for p in list_acb_files())
    unused_acb = [a for a in all_acb if a.lower() not in used_acb]
    if unused_acb:
        issues["unused_acb"] = unused_acb

    report_path = os.path.join(OUTPUT_DIR, "resource_audit.json")
    ensure_dir(OUTPUT_DIR)
    with open(report_path, "w", encoding="utf-8") as f:
        import json

        json.dump(
            {
                "summary": {
                    "hidden_charts": len(hidden_charts),
                    "orphan_charts": len(orphan_charts),
                    "failed_exports": len(failed_exports),
                    "unknown_keys": len(unknown_keys),
                    "unreferenced_bundles": len(unreferenced_bundles),
                    "unused_acb": len(unused_acb),
                },
                "details": issues,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    if not issues:
        print(Fore.GREEN + "资源完整性检查：未发现遗漏资源")
        return issues

    print(Fore.YELLOW + "资源完整性检查：发现可能需要关注的资源（详见 output/resource_audit.json）")
    if hidden_charts:
        print(Fore.YELLOW + f"  隐藏谱面 {len(hidden_charts)} 个（属于关卡但不在 chartIds 中）：")
        for item in hidden_charts[:20]:
            status = "已导出" if item["exported"] else "未导出"
            print(Fore.CYAN + f"    - {item['key']}（{item['level']}，{status}）")
        if len(hidden_charts) > 20:
            print(Fore.CYAN + f"    … 其余 {len(hidden_charts) - 20} 个见报告")
    if orphan_charts:
        print(Fore.YELLOW + f"  孤儿谱面 {len(orphan_charts)} 个（无对应关卡）：")
        for key in orphan_charts[:20]:
            print(Fore.CYAN + f"    - {key}")
        if len(orphan_charts) > 20:
            print(Fore.CYAN + f"    … 其余 {len(orphan_charts) - 20} 个见报告")
    if failed_exports:
        print(Fore.YELLOW + f"  导出失败资源 {len(failed_exports)} 个：")
        for item in failed_exports[:20]:
            print(Fore.CYAN + f"    - [{item['kind']}] {item['key']}")
        if len(failed_exports) > 20:
            print(Fore.CYAN + f"    … 其余 {len(failed_exports) - 20} 个见报告")
    if unknown_keys:
        print(Fore.YELLOW + f"  未知类型资源 {len(unknown_keys)} 个（可能未识别的新资源）：")
        for key in unknown_keys[:20]:
            print(Fore.CYAN + f"    - {key}")
        if len(unknown_keys) > 20:
            print(Fore.CYAN + f"    … 其余 {len(unknown_keys) - 20} 个见报告")
    if unreferenced_bundles:
        print(Fore.YELLOW + f"  未被 catalog/fileList 引用的 bundle {len(unreferenced_bundles)} 个（可能来自热更，建议确认）：")
        for name in unreferenced_bundles[:20]:
            print(Fore.CYAN + f"    - {name}")
        if len(unreferenced_bundles) > 20:
            print(Fore.CYAN + f"    … 其余 {len(unreferenced_bundles) - 20} 个见报告")
    if unused_acb:
        print(Fore.YELLOW + f"  未被关卡使用的 acb 音频 {len(unused_acb)} 个（已导出到 audio/）")
    return issues
