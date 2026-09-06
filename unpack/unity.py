import json
import os
import UnityPy
from unpack.paths import BUNDLES_DIR


def load_bundle(bundle_name: str):
    if not bundle_name:
        return None
    candidates = [
        os.path.join(BUNDLES_DIR, bundle_name),
        os.path.join(BUNDLES_DIR, os.path.basename(bundle_name)),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                return UnityPy.load(path)
            except Exception:
                return None
    return None


def iter_objects(env, type_names=None):
    if env is None:
        return
    wanted = set(type_names) if type_names else None
    for obj in env.objects:
        if wanted is None or obj.type.name in wanted:
            yield obj


def extract_text_assets(env):
    items = []
    for obj in iter_objects(env, ["TextAsset"]):
        data = obj.read()
        script = data.m_Script
        if isinstance(script, bytes):
            raw = script
        else:
            raw = str(script).encode("utf-8")
        items.append((data.m_Name, raw))
    return items


def extract_images(env):
    items = []
    seen = set()
    for obj in iter_objects(env, ["Texture2D", "Sprite"]):
        try:
            data = obj.read()
            name = getattr(data, "m_Name", "") or "image"
            image = getattr(data, "image", None)
        except Exception:
            continue
        if image is None:
            continue
        key = (name, getattr(image, "size", None))
        if key in seen:
            continue
        seen.add(key)
        items.append((name, image))
    return items


def extract_typetrees(env, name=None):
    items = []
    for obj in iter_objects(env, ["MonoBehaviour"]):
        data = obj.read()
        obj_name = getattr(data, "m_Name", "")
        if name is not None and obj_name != name:
            continue
        try:
            tree = obj.read_typetree()
        except Exception:
            continue
        items.append((obj_name, tree))
    return items


def extract_fonts(env):
    items = []
    for obj in iter_objects(env, ["Font"]):
        data = obj.read()
        name = getattr(data, "m_Name", "") or "font"
        blob = getattr(data, "m_FontData", None) or getattr(data, "m_Data", None)
        if blob:
            items.append((name, bytes(blob)))
    return items


def extract_video_clips(env):
    items = []
    for obj in iter_objects(env, ["VideoClip"]):
        data = obj.read()
        name = getattr(data, "m_Name", "") or "video"
        original = getattr(data, "m_OriginalPath", "") or ""
        ext = os.path.splitext(original)[1] or ".webm"
        resource = getattr(data, "m_ExternalResources", None)
        if resource is None:
            continue
        source = os.path.basename(resource.m_Source or "")
        blob = _read_streamed_resource(env, source, resource.m_Offset, resource.m_Size)
        if blob:
            items.append((name + ext, blob))
    return items


def _read_streamed_resource(env, source_name, offset, size):
    readers = []
    for file in env.files.values():
        nested = getattr(file, "files", None)
        if nested:
            for name, reader in nested.items():
                if name == source_name or name.endswith(source_name):
                    readers.append(reader)
        if getattr(file, "name", None) == source_name:
            readers.append(file)
    for reader in readers:
        try:
            reader.Position = offset
            data = reader.read(size)
            return bytes(data)
        except Exception:
            continue
    return b""


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False, separators=(",", ": "))


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
