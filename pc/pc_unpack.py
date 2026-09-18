"""Rizline PC (StandaloneWindows64) bundle unpacker.

Decrypts AES-256-CBC bundles, reads the Addressables catalog, discovers the
Default tables and exports charts / covers / audio / leftover assets by disc.

Requires: UnityPy, pycryptodome

Example:
    python pc/pc_unpack.py --game-data "D:/Rizline/Rizline_Data/Rizline_Data"
"""

import argparse
import base64
import hashlib
import json
import os
import re
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path

import UnityPy
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

HERE = Path(__file__).resolve().parent
DEFAULT_GAME_DATA = HERE / "Rizline_Data" / "Rizline_Data"
DEFAULT_OUT = HERE / "output"
TABLE_SCAN_MAX_BYTES = 1_000_000
PASSWORD = b"+rK3cH@3\txH|CR;b2\x00IP%O&w=j\r\n>N%sgQ1y"
SALT = bytes.fromhex("a76eb2f6ff88d70a74999ee77d762730")
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"


DISC_COLOR = {
    "Disc 1": C.CYAN,
    "Disc 2": C.BLUE,
    "EX - T.S.": C.MAGENTA,
    "EX - Single": C.YELLOW,
    "_unlisted": C.GRAY,
}


def paint(text, *cols):
    return "".join(cols) + str(text) + C.RESET


def enable_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if os.name != "nt":
        return
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if k32.GetConsoleMode(handle, ctypes.byref(mode)):
            k32.SetConsoleMode(handle, mode.value | 0x0004)
        k32.SetConsoleOutputCP(65001)
    except Exception:
        pass


def hr(ch="-", n=66):
    print(paint(ch * n, C.GRAY))


def banner():
    w = 64
    print(paint("+" + "=" * w + "+", C.MAGENTA, C.BOLD))
    print(
        paint("|", C.MAGENTA, C.BOLD)
        + paint("  RIZLINE Bundle Unpacker (PC)".ljust(w), C.WHITE, C.BOLD)
        + paint("|", C.MAGENTA, C.BOLD)
    )
    print(
        paint("|", C.MAGENTA, C.BOLD)
        + paint("  AES-256-CBC + PBKDF2-SHA256 / 3000 + LoopReverseXor".ljust(w), C.GRAY)
        + paint("|", C.MAGENTA, C.BOLD)
    )
    print(
        paint("|", C.MAGENTA, C.BOLD)
        + paint("  output/charts  output/audio  output/covers  output/other".ljust(w), C.CYAN)
        + paint("|", C.MAGENTA, C.BOLD)
    )
    print(paint("+" + "=" * w + "+", C.MAGENTA, C.BOLD))


def stage(n, title):
    print()
    print(paint(f"[{n}]", C.MAGENTA, C.BOLD) + " " + paint(title, C.WHITE, C.BOLD))


def bar(done, total, width=28):
    frac = 1.0 if total <= 0 else min(done / total, 1.0)
    filled = int(width * frac)
    return f"{C.CYAN}[{'#' * filled}{'-' * (width - filled)}]{C.RESET} {C.BOLD}{frac * 100:6.2f}%{C.RESET}"


def safe_name(name, fallback="unknown"):
    name = (name or "").strip() or fallback
    name = INVALID.sub("_", name).replace("\u3000", " ").strip(" .")
    return name[:120] or fallback


def bitrev(v):
    return int(f"{v:08b}"[::-1], 2)


def loop_reverse_xor(data):
    n = len(data)
    return bytes(bitrev(data[i]) ^ data[(i + 1) % n] for i in range(n))


def derive_key_iv():
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        loop_reverse_xor(PASSWORD),
        loop_reverse_xor(SALT),
        3000,
        48,
    )
    return dk[:32], dk[32:]


def decrypt_bundle(path, key, iv):
    ct = path.read_bytes()
    if len(ct) % 16 != 0:
        raise ValueError(f"{path.name}: length {len(ct)} not multiple of 16")
    return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16)


def parse_catalog(catalog_path):
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    blob = base64.b64decode(data["m_KeyDataString"])
    count = struct.unpack_from("<I", blob, 0)[0]
    off = 4
    keys = []
    for _ in range(count):
        ktype = blob[off]
        off += 1
        if ktype == 0:
            ln = struct.unpack_from("<I", blob, off)[0]
            off += 4
            keys.append(blob[off : off + ln].decode("ascii"))
            off += ln
        elif ktype == 1:
            ln = struct.unpack_from("<I", blob, off)[0]
            off += 4
            keys.append(blob[off : off + ln].decode("utf-16le"))
            off += ln
        else:
            keys.append(struct.unpack_from("<i", blob, off)[0])
            off += 4

    bucket = base64.b64decode(data["m_BucketDataString"])
    bcount = struct.unpack_from("<I", bucket, 0)[0]
    off = 4
    key_entries = []
    for _ in range(bcount):
        off += 4
        n = struct.unpack_from("<I", bucket, off)[0]
        off += 4
        idxs = list(struct.unpack_from("<%dI" % n, bucket, off))
        off += 4 * n
        key_entries.append(idxs)

    entry = base64.b64decode(data["m_EntryDataString"])
    ecount = struct.unpack_from("<I", entry, 0)[0]
    entries = [struct.unpack_from("<7i", entry, 4 + i * 28) for i in range(ecount)]
    iids = data["m_InternalIds"]

    key_to_bundle = {}
    for ki, k in enumerate(keys):
        if not isinstance(k, str):
            continue
        bundles = []
        for ei in key_entries[ki]:
            iid, _prov, dep, _h, _data, _pk, _rtype = entries[ei]
            bundle = None
            if 0 <= dep < len(keys) and isinstance(keys[dep], str) and keys[dep].endswith(".bundle"):
                bundle = keys[dep]
            elif 0 <= iid < len(iids):
                name = Path(iids[iid]).name
                if name.endswith(".bundle"):
                    bundle = name
            if bundle:
                bundles.append(bundle)
        if bundles:
            key_to_bundle[k] = list(dict.fromkeys(bundles))
    return key_to_bundle


class Extractor:
    def __init__(self, bundle_dir, aes_key, aes_iv):
        self.bundle_dir = bundle_dir
        self.aes_key = aes_key
        self.aes_iv = aes_iv
        self.cache = {}
        self.written = defaultdict(int)
        self.bytes_out = 0
        self.missing = defaultdict(list)

    def env(self, bundle_name):
        if bundle_name in self.cache:
            return self.cache[bundle_name]
        path = self.bundle_dir / bundle_name
        if not path.exists():
            self.cache[bundle_name] = None
            return None
        env = UnityPy.load(decrypt_bundle(path, self.aes_key, self.aes_iv))
        self.cache[bundle_name] = env
        return env

    def save_file(self, path, data, text=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        if text:
            raw = data.encode("utf-8")
            path.write_bytes(raw)
        else:
            raw = data
            path.write_bytes(raw)
        self.bytes_out += len(raw)
        return path

    def save_image(self, path, img):
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)
        self.bytes_out += path.stat().st_size
        return path

    def hardlink(self, src, dst):
        if src is None or not src.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            return
        try:
            os.link(src, dst)
        except OSError:
            import shutil

            shutil.copy2(src, dst)

    def export_text(self, env):
        for obj in env.objects:
            if obj.type.name != "TextAsset":
                continue
            data = obj.read()
            raw = getattr(data, "m_Script", None)
            if isinstance(raw, str):
                return raw
            if isinstance(raw, (bytes, bytearray)):
                return bytes(raw).decode("utf-8", errors="replace")
        return None

    def export_image(self, env):
        best = None
        best_area = -1
        for obj in env.objects:
            if obj.type.name not in {"Texture2D", "Sprite"}:
                continue
            try:
                data = obj.read()
                img = getattr(data, "image", None)
            except Exception:
                continue
            if img is None:
                continue
            area = img.size[0] * img.size[1]
            if area > best_area:
                best, best_area = img, area
        return best

    def export_audio(self, env):
        for obj in env.objects:
            if obj.type.name != "AudioClip":
                continue
            data = obj.read()
            samples = getattr(data, "samples", None) or {}
            if samples:
                name, raw = next(iter(samples.items()))
                raw = bytes(raw)
                ext = ".wav" if raw[:4] == b"RIFF" else ".bin"
                return raw, ext
            raw = getattr(data, "m_AudioData", None)
            if raw:
                return bytes(raw), ".bin"
        return None, None

    def from_keys(self, keys, kind):
        for k in keys:
            for bname in k:
                env = self.env(bname)
                if env is None:
                    continue
                if kind == "text":
                    val = self.export_text(env)
                    if val:
                        return val
                elif kind == "image":
                    val = self.export_image(env)
                    if val is not None:
                        return val
                elif kind == "audio":
                    raw, ext = self.export_audio(env)
                    if raw:
                        return raw, ext
        return None


def index_by_id(items):
    out = {}
    for item in items or []:
        if isinstance(item, dict) and item.get("id"):
            out[item["id"]] = item
    return out


class TableIndex:
    def __init__(self, name, bundle, tree):
        self.name = name
        self.bundle = bundle
        self.tree = tree
        self.levels = index_by_id(tree.get("levels"))
        self.disc_o = index_by_id(tree.get("discOLevels"))
        self.musics = index_by_id(tree.get("musics"))
        self.illustrations = index_by_id(tree.get("illustrations"))
        self.charts = index_by_id(tree.get("charts"))

    def slice(self, level_id, music_id, illustration_id, chart_ids):
        chart_ids = chart_ids or []
        return {
            "level": self.levels.get(level_id),
            "discOLevel": self.disc_o.get(level_id),
            "music": self.musics.get(music_id),
            "illustration": self.illustrations.get(illustration_id),
            "charts": [self.charts[c] for c in chart_ids if c in self.charts],
        }


def merge_latest(tables, attr):
    merged = {}
    for table in tables:
        merged.update(getattr(table, attr))
    return merged


def discover_tables(ex, scan_max_bytes=TABLE_SCAN_MAX_BYTES, scan_all=False):
    found = []
    bundles = sorted(ex.bundle_dir.glob("*.bundle"), key=lambda p: p.stat().st_size)
    if scan_all:
        small = bundles
    else:
        small = [p for p in bundles if p.stat().st_size <= scan_max_bytes]
    for i, path in enumerate(small, 1):
        try:
            env = ex.env(path.name)
        except Exception:
            continue
        if env is None:
            continue
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                continue
            if not (isinstance(tree, dict) and tree.get("m_Name") == "Default" and "levels" in tree):
                continue
            found.append((path.name, tree, obj.path_id, len(tree.get("levels") or [])))
        sys.stdout.write(
            f"\r  {bar(i, len(small))} "
            + paint(f"scan {i}/{len(small)}", C.GRAY)
            + paint(f"  tables={len(found)}", C.CYAN)
        )
        sys.stdout.flush()
    print()
    found.sort(key=lambda x: (x[3], x[0]))
    tables = []
    for i, (bname, tree, _pid, _n) in enumerate(found, 1):
        name = "Default" if i == 1 else f"Default_{i}"
        tables.append(TableIndex(name, bname, tree))
    return tables


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Rizline PC bundle unpacker")
    parser.add_argument(
        "--game-data",
        type=Path,
        default=DEFAULT_GAME_DATA,
        help="Rizline_Data folder that contains StreamingAssets/aa",
    )
    parser.add_argument("--bundle-dir", type=Path, default=None, help="folder with *.bundle (overrides --game-data)")
    parser.add_argument("--catalog", type=Path, default=None, help="path to catalog.json (overrides --game-data)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument("--scan-max-bytes", type=int, default=TABLE_SCAN_MAX_BYTES, help="max bundle size to scan for Default tables")
    parser.add_argument("--scan-all", action="store_true", help="scan every bundle for Default tables")
    return parser


def main():
    args = build_arg_parser().parse_args()
    enable_console()
    banner()
    t0 = time.perf_counter()

    if args.bundle_dir is not None:
        bundle_dir = args.bundle_dir
    else:
        bundle_dir = args.game_data / "StreamingAssets" / "aa" / "StandaloneWindows64"
    if args.catalog is not None:
        catalog_path = args.catalog
    else:
        catalog_path = args.game_data / "StreamingAssets" / "aa" / "catalog.json"
    out = args.out

    if not bundle_dir.is_dir():
        raise SystemExit(f"bundle dir not found: {bundle_dir}")
    if not catalog_path.is_file():
        raise SystemExit(f"catalog not found: {catalog_path}")

    print(paint("  bundles ", C.GRAY) + paint(bundle_dir, C.CYAN))
    print(paint("  catalog ", C.GRAY) + paint(catalog_path, C.CYAN))
    print(paint("  output  ", C.GRAY) + paint(out, C.YELLOW))

    stage(1, "derive AES-256 key")
    aes_key, aes_iv = derive_key_iv()
    print(paint("  key ", C.GRAY) + paint(aes_key.hex()[:32] + "...", C.CYAN))
    print(paint("  iv  ", C.GRAY) + paint(aes_iv.hex(), C.CYAN))

    stage(2, "parse Addressables catalog")
    key_map = parse_catalog(catalog_path)
    n_chart = sum(1 for k in key_map if k.startswith("chart."))
    n_ill = sum(1 for k in key_map if k.startswith("illustration."))
    n_music = sum(1 for k in key_map if k.startswith("music."))
    print(
        paint("  keys ", C.GRAY)
        + paint(len(key_map), C.CYAN, C.BOLD)
        + paint("  chart=", C.GRAY)
        + paint(n_chart, C.YELLOW)
        + paint("  ill=", C.GRAY)
        + paint(n_ill, C.BLUE)
        + paint("  music=", C.GRAY)
        + paint(n_music, C.MAGENTA)
    )

    stage(3, "discover Default tables")
    ex = Extractor(bundle_dir, aes_key, aes_iv)
    tables = discover_tables(ex, args.scan_max_bytes, args.scan_all)
    if not tables:
        raise SystemExit("no Default tables found")
    (out / "meta").mkdir(parents=True, exist_ok=True)
    for table in tables:
        print(
            paint(f"  {table.name.ljust(12)}", C.GRAY)
            + paint(table.bundle[:16] + "...", C.DIM)
            + paint(f"  levels={len(table.levels)}", C.CYAN, C.BOLD)
            + paint(f"  charts={len(table.charts)}", C.YELLOW)
            + paint(f"  discO={len(table.disc_o)}", C.MAGENTA)
        )
        ex.save_file(
            out / "meta" / f"{table.name}.json",
            json.dumps(table.tree, ensure_ascii=False, indent=2),
            text=True,
        )

    musics = merge_latest(tables, "musics")
    charts_meta = merge_latest(tables, "charts")
    ill_meta = merge_latest(tables, "illustrations")
    level_map = merge_latest(tables, "levels")
    disco_map = merge_latest(tables, "disc_o")
    levels = list(level_map.values()) + [v for k, v in disco_map.items() if k not in level_map]
    discs = sorted({lv.get("discName") or "Unknown" for lv in levels})
    print(
        paint("  merged ", C.GRAY)
        + paint(f"tables={len(tables)}", C.WHITE, C.BOLD)
        + paint(f"  songs={len(levels)}", C.CYAN, C.BOLD)
        + paint(f"  charts={len(charts_meta)}", C.YELLOW, C.BOLD)
        + paint("  discs ", C.GRAY)
        + paint(", ".join(discs), C.MAGENTA)
    )

    for name in ("charts", "audio", "covers", "other"):
        (out / name).mkdir(parents=True, exist_ok=True)

    stage(4, "unpack + classify by disc")
    used_keys = set()
    disc_songs = defaultdict(int)
    official_chart_ids = set()
    song_lookup = {}

    for i, lv in enumerate(levels, 1):
        mid = lv["id"]
        music = musics.get(lv["musicId"], {})
        song = music.get("musicName") or mid.split(".")[0]
        artist = music.get("artist") or ""
        disc = lv.get("discName") or "Unknown"
        disc_songs[disc] += 1
        folder_name = safe_name(f"{song} [{artist}]" if artist else song)
        song_dir = out / "charts" / safe_name(disc) / folder_name
        song_dir.mkdir(parents=True, exist_ok=True)

        info = {
            "id": mid,
            "disc": disc,
            "musicName": song,
            "artist": artist,
            "illustrationId": lv.get("illustrationId"),
            "illustrationArtist": (ill_meta.get(lv.get("illustrationId", "")) or {}).get("artist"),
            "chartIds": lv.get("chartIds", []),
            "charts": [charts_meta[c] for c in lv.get("chartIds", []) if c in charts_meta],
            "tables": {
                t.name: t.slice(mid, lv.get("musicId"), lv.get("illustrationId"), lv.get("chartIds"))
                for t in tables
            },
        }
        rel = str(song_dir.relative_to(out)).replace("\\", "/")
        song_lookup[mid] = {
            "path": rel,
            "disc": disc,
            "musicName": song,
            "artist": artist,
            "tables": [t.name for t in tables if t.levels.get(mid) or t.disc_o.get(mid)],
        }
        ex.save_file(song_dir / "meta.json", json.dumps(info, ensure_ascii=False, indent=2), text=True)
        ex.written["meta"] += 1

        iid = lv.get("illustrationId")
        if iid:
            used_keys.add(iid)
            used_keys.add(f"{iid}.HiRes")
        img = None
        candidates = []
        if iid:
            candidates.append(f"{iid}.HiRes")
            candidates.append(iid)
        if mid:
            candidates.append(f"altIllustration.{mid}")
        for k in candidates:
            used_keys.add(k)
            img = ex.from_keys([key_map.get(k, [])], "image")
            if img is not None:
                break
        cover_path = None
        if img is not None:
            cover_path = ex.save_image(song_dir / "cover.png", img)
            ex.hardlink(cover_path, out / "covers" / safe_name(disc) / f"{folder_name}.png")
            ex.written["cover"] += 1
        else:
            ex.missing["cover"].append(mid)

        music_key = f"music.{lv.get('musicId') or mid}"
        used_keys.add(music_key)
        audio = ex.from_keys([key_map.get(music_key, [])], "audio")
        if audio:
            raw, ext = audio
            audio_path = ex.save_file(song_dir / f"audio{ext}", raw)
            ex.hardlink(audio_path, out / "audio" / safe_name(disc) / f"{folder_name}{ext}")
            ex.written["audio"] += 1
        else:
            ex.missing["audio"].append(mid)

        for cid in lv.get("chartIds", []):
            official_chart_ids.add(cid)
            used_keys.add(cid)
            cm = charts_meta.get(cid, {})
            diff = cm.get("level") or cid.rsplit(".", 1)[-1]
            text = ex.from_keys([key_map.get(cid, [])], "text")
            if text:
                ex.save_file(song_dir / f"{safe_name(diff)}.json", text, text=True)
                ex.written["chart"] += 1
            else:
                ex.missing["chart"].append(cid)

        elapsed = time.perf_counter() - t0
        rate = i / elapsed if elapsed else 0
        eta = (len(levels) - i) / rate if rate else 0
        col = DISC_COLOR.get(disc, C.WHITE)
        sys.stdout.write(
            f"\r  {bar(i, len(levels))} "
            + paint(f"{i}/{len(levels)}", C.WHITE, C.BOLD)
            + " "
            + paint(disc, col)
            + paint(f"  files={sum(ex.written.values())}", C.GREEN)
            + paint(f"  eta={eta:5.0f}s ", C.YELLOW)
        )
        sys.stdout.flush()
    print()

    stage(5, "export leftover catalog assets")
    leftover = 0
    leftovers = [
        (k, bs)
        for k, bs in key_map.items()
        if k not in used_keys and k.split(".")[0] in {"chart", "illustration", "altIllustration", "music", "uisound"}
    ]
    for j, (k, bundles) in enumerate(leftovers, 1):
        prefix = k.split(".", 1)[0]
        dest_root = out / "other" / prefix
        name = safe_name(k)
        if prefix == "chart":
            text = ex.from_keys([bundles], "text")
            if text:
                ex.save_file(dest_root / f"{name}.json", text, text=True)
                leftover += 1
        elif prefix in {"illustration", "altIllustration"}:
            img = ex.from_keys([bundles], "image")
            if img is not None:
                ex.save_image(dest_root / f"{name}.png", img)
                leftover += 1
        elif prefix in {"music", "uisound"}:
            audio = ex.from_keys([bundles], "audio")
            if audio:
                raw, ext = audio
                ex.save_file(dest_root / f"{name}{ext}", raw)
                leftover += 1
        if j == len(leftovers) or j % 20 == 0:
            sys.stdout.write(f"\r  {bar(j, len(leftovers))} " + paint(f"{j}/{len(leftovers)} leftover", C.GRAY))
            sys.stdout.flush()
    print()

    elapsed = time.perf_counter() - t0
    index = {
        "songs": len(levels),
        "tables": [
            {"name": t.name, "bundle": t.bundle, "levels": len(t.levels), "charts": len(t.charts), "discO": len(t.disc_o)}
            for t in tables
        ],
        "discs": dict(disc_songs),
        "written": dict(ex.written),
        "leftover": leftover,
        "bytes": ex.bytes_out,
        "elapsed": elapsed,
        "missing": {k: v for k, v in ex.missing.items() if v},
        "byId": song_lookup,
    }
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "meta" / "lookup.json").write_text(json.dumps(song_lookup, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    hr()
    print(paint(" SUMMARY", C.WHITE, C.BOLD))
    hr()
    rows = [
        ("output", str(out), C.YELLOW),
        ("tables", len(tables), C.WHITE),
        ("songs", len(levels), C.CYAN),
        ("charts written", ex.written["chart"], C.GREEN),
        ("covers written", ex.written["cover"], C.BLUE),
        ("audio written", ex.written["audio"], C.MAGENTA),
        ("leftover assets", leftover, C.GRAY),
        ("bytes", f"{ex.bytes_out / 1024 / 1024:.2f} MB", C.YELLOW),
        ("elapsed", f"{elapsed:.1f}s", C.BLUE),
    ]
    for label, val, col in rows:
        print(f"  {paint(label.ljust(18), C.GRAY)} {paint(val, col, C.BOLD)}")
    print()
    print(paint(" discs", C.WHITE, C.BOLD))
    for disc, n in sorted(disc_songs.items(), key=lambda x: (-x[1], x[0])):
        col = DISC_COLOR.get(disc, C.WHITE)
        print(f"  {paint('*', col)} {paint(disc.ljust(16), col)} {paint(n, C.WHITE, C.BOLD)} songs")
        print(f"      {paint(str(out / 'charts' / safe_name(disc)), C.GRAY)}")
    if any(ex.missing.values()):
        print()
        print(paint(" missing", C.RED, C.BOLD))
        for kind, items in ex.missing.items():
            if not items:
                continue
            print(f"  {paint(kind, C.YELLOW)} {paint(len(items), C.RED, C.BOLD)}")
            for item in items[:5]:
                print(f"    {paint(item, C.GRAY)}")
        raise SystemExit(1)
    print()
    print(paint("DONE  python pc/pc_unpack.py", C.GREEN, C.BOLD))
    print(paint(f"  -> {out / 'charts'}", C.CYAN))


if __name__ == "__main__":
    main()
