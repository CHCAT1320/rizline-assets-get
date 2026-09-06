import os
from unpack.paths import safe_filename


def classify_key(key: str) -> tuple:
    if not isinstance(key, str):
        return ("skip", None)
    if key.endswith(".bundle") or (len(key) == 32 and all(c in "0123456789abcdef" for c in key)):
        return ("skip", None)
    if key.startswith("chart."):
        return ("chart", _chart_relpath(key))
    if key.startswith("illustration."):
        return ("illustration", _image_relpath("illustrations", key))
    if key.startswith("altIllustration."):
        return ("alt_illustration", _image_relpath("alt_illustrations", key))
    if key.startswith("layout."):
        return ("layout", _image_relpath("layouts", key))
    if key.startswith("seriesBanner."):
        return ("series_banner", os.path.join("series", "banners", safe_filename(key) + ".png"))
    if key.startswith("seriesPoster."):
        return ("series_poster", os.path.join("series", "posters", safe_filename(key) + ".png"))
    if key.startswith("avatar."):
        return ("avatar", os.path.join("avatars", safe_filename(key) + ".png"))
    if key.startswith("banner."):
        if key == "banner.bannerList":
            return ("banner_config", os.path.join("banners", "bannerList.json"))
        return ("banner", os.path.join("banners", safe_filename(key) + ".png"))
    if key.startswith("local.") or key.startswith("predownload_"):
        return ("localization", os.path.join("localization", safe_filename(key) + ".txt"))
    if key.startswith("D00"):
        return ("video", os.path.join("videos", safe_filename(key)))
    if key.startswith("Assets/Rizline/") or key.startswith("Assets/Le Tai"):
        if key.lower().endswith((".mat", ".prefab")):
            return ("skip", None)
        return ("ui_asset", _assets_relpath(key))
    return ("skip", None)


def _chart_relpath(key: str) -> str:
    parts = key.split(".")
    # chart.<song>.<artist>.<n>.<diff>
    # chart.<song>.<artist>.<n>.mr.<diff>
    # chart.<song>.<artist>.<n>.cn.<diff>
    # chart.challenge.<id>.Chart
    if len(parts) >= 3 and parts[1] == "challenge":
        return os.path.join("charts", "challenge", f"{key}.json")
    song = parts[1] if len(parts) > 1 else key
    extras = []
    if ".mr." in key:
        extras.append("mr")
    if ".cn." in key:
        extras.append("cn")
    folder = os.path.join("charts", "_catalog", song)
    if extras:
        folder = os.path.join(folder, "_".join(extras))
    return os.path.join(folder, f"{key}.json")


def _image_relpath(root: str, key: str) -> str:
    suffix = []
    name = key
    if name.endswith(".HiRes"):
        suffix.append("HiRes")
        name = name[: -len(".HiRes")]
    if name.endswith(".cn"):
        suffix.append("cn")
        name = name[: -len(".cn")]
    filename = safe_filename(key) + ".png"
    if suffix:
        return os.path.join(root, safe_filename(name), "_".join(suffix), filename)
    return os.path.join(root, safe_filename(name), filename)


def _assets_relpath(key: str) -> str:
    rel = key
    prefixes = ["Assets/Rizline/", "Assets/Le Tai's Asset/"]
    for prefix in prefixes:
        if rel.startswith(prefix):
            rel = rel[len(prefix) :]
            break
    return os.path.join("ui", rel.replace("\\", "/"))
