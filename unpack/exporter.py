from collections import Counter
import os
from colorama import Fore
from unpack.audio import find_acb
from unpack.catalog import build_bundle_map
from unpack.classify import classify_key
from unpack.exporters import (
    extra_charts_for_level,
    export_catalog_asset,
    export_level_pack,
    export_remaining_audio,
)
from unpack.levels import all_levels, load_default


def export_all_resources():
    data = load_default()
    bundle_map = build_bundle_map()
    levels = all_levels(data)
    extra_map = {level["id"]: extra_charts_for_level(level, bundle_map) for level in levels}
    used_acb = []

    print(Fore.GREEN + f"开始导出 {len(levels)} 个关卡资源")
    for i, level in enumerate(levels, 1):
        extras = extra_map.get(level["id"], [])
        result = export_level_pack(level, data, bundle_map, extra_chart_ids=extras)
        acb_path = find_acb(level["id"].split(".")[0])
        if acb_path:
            used_acb.append(os.path.basename(acb_path))
        extra_note = f" +{len(extras)}热更新谱面" if extras else ""
        wav_note = "" if result["wav"] else "（无音频）"
        print(
            f"{Fore.GREEN}关卡导出：{Fore.YELLOW}{i}/{len(levels)} {Fore.CYAN}{result['disc']}/{result['name']} "
            f"{Fore.GREEN}成功 谱面{result['charts']}{extra_note}{wav_note}",
            flush=True,
        )

    assigned_charts = set()
    for extras in extra_map.values():
        assigned_charts.update(extras)
    for level in levels:
        assigned_charts.update(level.get("chartIds", []))

    stats = Counter()
    skipped_charts = 0
    catalog_keys = [(key, bundle_name) for key, bundle_name in bundle_map.items() if classify_key(key)[0] != "skip"]
    print(Fore.GREEN + f"开始导出分类资源 {len(catalog_keys)} 项", flush=True)
    for i, (key, bundle_name) in enumerate(catalog_keys, 1):
        kind, _ = classify_key(key)
        if kind == "chart" and key in assigned_charts:
            skipped_charts += 1
            continue
        exported_kind, count = export_catalog_asset(key, bundle_name)
        if count:
            stats[exported_kind] += count
        else:
            stats[f"{exported_kind}_failed"] += 1
        if i % 50 == 0 or i == len(catalog_keys):
            print(Fore.CYAN + f"分类导出：{i}/{len(catalog_keys)}", flush=True)

    print(Fore.GREEN + "开始转换未进关卡的音频", flush=True)
    leftover_audio, failed_audio = export_remaining_audio(used_acb)

    print(Fore.GREEN + "分类资源导出完成：")
    labels = {
        "chart": "额外谱面",
        "illustration": "曲绘",
        "alt_illustration": "替代曲绘",
        "layout": "铺面背景",
        "series_banner": "系列横幅",
        "series_poster": "系列海报",
        "avatar": "头像",
        "banner": "活动Banner图",
        "banner_config": "Banner配置",
        "localization": "本地化",
        "video": "视频",
        "ui_asset": "UI资源",
    }
    for kind, label in labels.items():
        if stats[kind]:
            print(Fore.CYAN + f"  {label}: {stats[kind]}")
    print(Fore.CYAN + f"  其余音频: {leftover_audio}")
    failed = {k: v for k, v in stats.items() if k.endswith("_failed") and v}
    if failed_audio:
        failed["audio_failed"] = failed_audio
    if failed:
        print(Fore.YELLOW + "  部分资源未能导出：")
        for k, v in failed.items():
            print(Fore.YELLOW + f"    {k}: {v}")
    print(Fore.GREEN + f"已随关卡导出的谱面：{skipped_charts}")
