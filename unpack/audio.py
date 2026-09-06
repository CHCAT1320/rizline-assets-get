import os
import platform
import shutil
import subprocess
from unpack.paths import ACB_DIR, ROOT


def vgmstream_path() -> str:
    system = platform.system()
    if system == "Windows":
        return os.path.join(ROOT, "vgmstream-cli", "vgmstream-cli.exe")
    local_path = os.path.join(ROOT, "vgmstream-cli", "vgmstream-cli")
    if os.path.exists(local_path):
        return local_path
    if shutil.which("vgmstream-cli"):
        return "vgmstream-cli"
    raise FileNotFoundError("未找到 vgmstream-cli，请确保已安装或在 ./vgmstream-cli/ 目录下")


def find_acb(level_name: str):
    if not os.path.isdir(ACB_DIR):
        return None
    target = level_name.lower()
    exact = None
    prefix = None
    for filename in os.listdir(ACB_DIR):
        stem = filename.split(".")[0].lower()
        if stem == target:
            exact = os.path.join(ACB_DIR, filename)
            break
        if prefix is None and (stem.startswith(target) or target.startswith(stem)):
            prefix = os.path.join(ACB_DIR, filename)
    return exact or prefix


def list_acb_files():
    if not os.path.isdir(ACB_DIR):
        return []
    return [
        os.path.join(ACB_DIR, name)
        for name in os.listdir(ACB_DIR)
        if name.lower().endswith(".acb")
    ]


def convert_acb_to_wav(acb_path: str, wav_path: str) -> bool:
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    cli = vgmstream_path()
    result = subprocess.run(
        [cli, "-o", wav_path, acb_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0 and os.path.exists(wav_path):
        return True
    tmp_dir = os.path.join(ROOT, "download", "_vgm_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_acb = os.path.join(tmp_dir, "src.acb")
    tmp_wav = os.path.join(tmp_dir, "out.wav")
    shutil.copyfile(acb_path, tmp_acb)
    result = subprocess.run(
        [cli, "-o", tmp_wav, tmp_acb],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ok = result.returncode == 0 and os.path.exists(tmp_wav)
    if ok:
        shutil.copyfile(tmp_wav, wav_path)
    for path in (tmp_acb, tmp_wav):
        if os.path.exists(path):
            os.remove(path)
    return ok and os.path.exists(wav_path)
