import os
from unpack.audio import convert_acb_to_wav, find_acb, list_acb_files
from unpack.classify import classify_key
from unpack.paths import BUNDLES_DIR, CHARTS_DIR, OUTPUT_DIR, ensure_dir, safe_filename
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
            return kind, export_video(env, dest)
        if kind == "ui_asset":
            return kind, export_ui_asset(env, dest)
        exporter = TYPE_EXPORTERS.get(kind)
        if exporter is None:
            return kind, 0
        return kind, exporter(env, dest)
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


def export_bundle_contents(bundle_name, dest_dir):
    try:
        env = load_bundle(bundle_name)
        if env is None:
            return 0
        count = 0
        ensure_dir(dest_dir)
        for name, image in extract_images(env):
            path = os.path.join(dest_dir, safe_filename(name) + ".png")
            image.save(path)
            count += 1
        for name, raw in extract_text_assets(env):
            ext = ".json" if raw.lstrip().startswith(b"{") or raw.lstrip().startswith(b"[") else ".txt"
            path = os.path.join(dest_dir, safe_filename(name) + ext)
            write_bytes(path, raw)
            count += 1
        for name, tree in extract_typetrees(env):
            path = os.path.join(dest_dir, safe_filename(name or "MonoBehaviour") + ".json")
            write_json(path, tree)
            count += 1
        for name, blob in extract_fonts(env):
            path = os.path.join(dest_dir, safe_filename(name) + ".ttf")
            write_bytes(path, blob)
            count += 1
        for name, blob in extract_video_clips(env):
            path = os.path.join(dest_dir, safe_filename(name))
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
