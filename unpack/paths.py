import os


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOWNLOAD_DIR = os.path.join(ROOT, "download")
BUNDLES_DIR = os.path.join(DOWNLOAD_DIR, "bundles")
ACB_DIR = os.path.join(DOWNLOAD_DIR, "acb")
CATALOG_PATH = os.path.join(DOWNLOAD_DIR, "catalog_catalog.json")
FILELIST_PATH = os.path.join(DOWNLOAD_DIR, "fileList.json")
OUTPUT_DIR = os.path.join(ROOT, "output")
DEFAULT_JSON = os.path.join(OUTPUT_DIR, "default.json")
CHARTS_DIR = os.path.join(OUTPUT_DIR, "charts")


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    return str(name).replace("/", "_").replace("\\", "_")
