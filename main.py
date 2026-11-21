import requests
import json
import os
import shutil
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

from colorama import init, Fore, Style
from unpack import export_all_resources, parse_catalog, parse_level

init(autoreset=True)

# 获取Rizline版本号
def getRizlineVersion() -> dict:
    url = "https://rizserver.pigeongames.net/game/server_api/v1/dis/"
    # 设置请求头 ==> game_id: pigeongames.rizline, channel_id: 11, i18n: zh-CN
    headers = {
        "host": "rizserver.pigeongames.net",
        "game_id": "pigeongames.rizline",
        "channel_id": "11",
        "i18n": "zh-CN",
        "accept-encoding": "gzip, identity",
        "user-agent": "BestHTTP/2 v2.6.3",
        "content-length": "0"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = json.loads(response.text)
        result = {
            "version": data["configs"][0]["version"],
            "resourceUrl": data["configs"][0]["resourceUrl"],
            "resourceBaseUrl" : data["configs"][0]["resourceBaseUrl"],
            "resourceVersion": data["configs"][0]["resourceVersion"],
            "minimalVersion": data["minimalVersion"]
        }
        print(
                Fore.GREEN + "Rizline版本号：" + result["version"]
                + "\nRizline资源URL：" + result["resourceUrl"]
                + "\nRizline资源基础URL：" + result["resourceBaseUrl"]
                + "\nRizline资源版本号：" + result["resourceVersion"]
                + "\nRizline最低版本号：" + result["minimalVersion"]
            )
        return result
    else:
        print(Fore.RED + "获取Rizline版本号失败")
        return None

CHUNK_SIZE = 1024 * 1024  # 分块大小：1MB/块（平衡速度和进度刷新频率）
PROGRESS_BAR_FIXED_LENGTH = 20  # 进度条固定字符数，可按需调整（如15/25）
MAX_FILENAME_DISPLAY = 40       # 文件名最大显示长度，超长截断，避免挤压进度条
MAX_WORKERS = 16                # 并发下载线程数
print_lock = threading.Lock()   # 并发打印锁，避免输出乱码

def format_file_size(size: int) -> str:
    """格式化文件大小（B/KB/MB/GB），保留2位小数"""
    units = ['B', 'KB', 'MB', 'GB']
    unit_idx = 0
    size_float = float(size)
    while size_float >= 1024 and unit_idx < 3:
        size_float /= 1024
        unit_idx += 1
    return f"{size_float:.2f}{units[unit_idx]}"

def single_file_progress(downloaded: int, total: int, file_name: str, start_time: float):
    """
    单文件进度条（固定长度+恢复青色箭头+单位统一+防超100%）
    进度条结构：[=====>          ]  总长度固定为PROGRESS_BAR_FIXED_LENGTH
    """
    if total == 0:
        return
    
    # 核心：限制进度不超过100%，单位统一（纯字节计算）
    downloaded = min(downloaded, total)
    progress_ratio = downloaded / total
    filled_count = int(PROGRESS_BAR_FIXED_LENGTH * progress_ratio)

    # 1. 恢复箭头逻辑：进度未满→显示青色箭头，满了→无箭头
    arrow = Fore.CYAN + ">" if filled_count < PROGRESS_BAR_FIXED_LENGTH else ""
    # 2. 计算填充/空白字符：保证进度条总长度严格固定
    filled = Fore.MAGENTA + "=" * filled_count
    empty = " " * (PROGRESS_BAR_FIXED_LENGTH - filled_count - (1 if arrow else 0))
    # 3. 拼接固定长度进度条（填充+箭头+空白 总长度=PROGRESS_BAR_FIXED_LENGTH）
    progress_bar = f"[{filled}{arrow}{empty}{Fore.WHITE}]"

    # 长文件名处理：截断中间+保留后缀+固定显示宽度（避免晃动）
    if len(file_name) > MAX_FILENAME_DISPLAY:
        suffix = file_name[file_name.rfind('.'):] if '.' in file_name else ''
        prefix_len = MAX_FILENAME_DISPLAY - len(suffix) - 3  # 3=省略号...
        file_name_display = f"{file_name[:prefix_len]}...{suffix}"
    else:
        file_name_display = file_name
    file_name_fixed = f"{file_name_display:<{MAX_FILENAME_DISPLAY}}"  # 左对齐+补空格

    # 格式化百分比/大小/下载速度
    percentage = Fore.RED + f"{progress_ratio:.1%}" + Style.RESET_ALL
    size_info = f"{format_file_size(downloaded)}/{format_file_size(total)}"
    elapsed_time = max(time.time() - start_time, 0.001)  # 避免除0
    speed_info = Fore.GREEN + f"{format_file_size(downloaded/elapsed_time)}/s" + Style.RESET_ALL

    # 单行覆盖打印（flush强制刷新，end=''不换行）
    print(f"\r下载中：{file_name_fixed} {progress_bar} {percentage} | {size_info} | 速度：{speed_info}",
          end='', flush=True)


class MultiProgress:
    """
    多行并发进度显示：
    - 顶部为活跃下载线程各自的一行进度（最多 MAX_WORKERS 行）
    - 底部为整批总进度条（文件数 + 总字节数）
    使用 ANSI 光标控制原地重绘，所有更新都在锁内完成，避免多线程串行错乱。
    """

    def __init__(self, total_files: int, slots: int = MAX_WORKERS):
        self.total_files = total_files
        self.slots = slots
        self.lock = threading.Lock()
        self.slots_state = {}  # slot_id -> {"name", "downloaded", "total", "start"}
        self.completed = 0
        self.failed = 0
        self.total_bytes = 0
        self.done_bytes = 0
        self.batch_start = time.time()
        self.lines_rendered = 0
        self.enabled = True

    # 占用一个显示槽位并登记文件信息
    def start_file(self, slot_id: int, name: str):
        with self.lock:
            self.slots_state[slot_id] = {
                "name": name,
                "downloaded": 0,
                "total": 0,
                "start": time.time(),
            }
            self._render()

    # 收到响应头后登记文件总大小（同槽位重试时覆盖，不重复累加）
    def set_total(self, slot_id: int, total: int):
        with self.lock:
            state = self.slots_state.get(slot_id)
            if state is None:
                return
            total = max(total, 0)
            self.total_bytes += total - state["total"]
            state["total"] = total
            self._render()

    # 更新某个文件的已下载字节
    def update_file(self, slot_id: int, downloaded: int):
        with self.lock:
            state = self.slots_state.get(slot_id)
            if state is None:
                return
            state["downloaded"] = downloaded
            self._render()

    # 结束块内某一槽位（成功或失败），并打印一条独立日志（如失败信息）
    def print_line(self, text: str):
        with self.lock:
            if not self.enabled:
                print(text, flush=True)
                return
            # 光标位于块顶：用 \033[J 清掉整块，在该位置打印日志，再在下方重绘块
            parts = []
            if self.lines_rendered:
                parts.append("\033[J")
            parts.append(text + "\n")
            print("".join(parts), end="", flush=True)
            self.lines_rendered = 0
            self._render()

    # 某个文件结束（成功或失败），释放槽位
    def finish_file(self, slot_id: int, success: bool):
        with self.lock:
            state = self.slots_state.pop(slot_id, None)
            if state is not None:
                self.done_bytes += state.get("downloaded", 0)
            self.completed += 1
            if not success:
                self.failed += 1
            self._render()

    def _bar(self, ratio: float, length: int = PROGRESS_BAR_FIXED_LENGTH) -> str:
        ratio = max(0.0, min(ratio, 1.0))
        filled = int(length * ratio)
        arrow = Fore.CYAN + ">" if filled < length else ""
        filled_str = Fore.MAGENTA + "=" * filled
        empty = " " * (length - filled - (1 if arrow else 0))
        return f"[{filled_str}{arrow}{empty}{Fore.WHITE}]"

    @staticmethod
    def _short_name(name: str) -> str:
        if len(name) > MAX_FILENAME_DISPLAY:
            suffix = name[name.rfind('.'):] if '.' in name else ''
            prefix_len = MAX_FILENAME_DISPLAY - len(suffix) - 3
            name = f"{name[:prefix_len]}...{suffix}"
        return f"{name:<{MAX_FILENAME_DISPLAY}}"

    def _render(self):
        if not self.enabled:
            return
        # 已在锁内调用，无需再加锁。
        # 只渲染「活跃文件行 + 1 个总行」，块高度随活跃下载数动态变化，
        # 不再用空行占位，避免文件数不足 16 个时出现大片空白。
        body = []
        for slot_id in sorted(self.slots_state.keys()):
            state = self.slots_state[slot_id]
            total = state["total"]
            downloaded = state["downloaded"]
            ratio = downloaded / total if total > 0 else 0.0
            elapsed = max(time.time() - state["start"], 0.001)
            speed = format_file_size(downloaded / elapsed)
            size_info = (
                f"{format_file_size(downloaded)}/{format_file_size(total)}"
                if total > 0
                else format_file_size(downloaded)
            )
            body.append(
                f"  {self._short_name(state['name'])} {self._bar(ratio)} "
                f"{Fore.RED}{ratio:.0%}{Style.RESET_ALL} | {size_info} | "
                f"{Fore.GREEN}{speed}/s{Style.RESET_ALL}"
            )

        total_ratio = self.completed / self.total_files if self.total_files > 0 else 0.0
        elapsed = max(time.time() - self.batch_start, 0.001)
        total_speed = format_file_size(self.done_bytes / elapsed)
        body.append(
            Fore.YELLOW
            + f"总进度 {self.completed}/{self.total_files} {self._bar(total_ratio, 30)} "
            + f"{total_ratio:.1%} | 失败 {self.failed} | {format_file_size(self.done_bytes)} "
            + f"| {total_speed}/s"
            + Style.RESET_ALL
        )

        height = len(body)
        # 不变量：调用 _render 时光标已位于块顶（第一行行首）。
        # 因此这里不再上移，直接原地重写；最后一行不输出多余换行，避免触发终端滚动造成光标漂移。
        parts = []
        for i, line in enumerate(body):
            parts.append(line)
            parts.append("\033[K")  # 清除该行残留
            if i < height - 1:
                parts.append("\n")
        parts.append("\033[J")  # 清除块下方残留的旧行（块变矮时擦掉多余行）
        if height > 1:
            parts.append(f"\033[{height - 1}A")  # 回到块顶
        parts.append("\r")  # 回到行首
        print("".join(parts), end="", flush=True)
        self.lines_rendered = height

    # 结束时收尾：把光标移到块下方并换行，恢复后续正常输出
    def close(self):
        with self.lock:
            if self.enabled and self.lines_rendered:
                # 光标停在块顶，下移到块的最后一行再换行
                if self.lines_rendered > 1:
                    print(f"\033[{self.lines_rendered - 1}B", end="", flush=True)
                print()
            self.lines_rendered = 0
            self.enabled = False


# 下载单个文件 ==> 保存到本地
def downloadFile(url: str, session=None, show_progress=True, progress_slot=None) -> tuple:
    root_download_dir = "./download"
    file_name = url.split("/")[-1]
    save_dir = root_download_dir
    is_catalog = file_name.endswith("catalog_catalog.json")

    # 注意：.acb= 判断必须放在 endswith("bundle") 之前，
    # 因为 CRI 音频 bundle 的 URL 形如 xxx.acb=3c2b40.bundle，
    # 若先命中 bundle 分支会被错误地存入 bundles/ 且文件名带 =hash 后缀。
    if ".acb=" in url:
        save_dir = os.path.join(root_download_dir, "acb")
        file_name = file_name.split(".acb=")[0] + ".acb"
    elif url.endswith("bundle"):
        save_dir = os.path.join(root_download_dir, "bundles")

    file_full_path = os.path.join(save_dir, file_name)

    # 已存在且非空才视为已完成；0 字节残留一律重下。
    # catalog 文件每次都强制重下（内容会随版本变化）。
    if not is_catalog and os.path.exists(file_full_path) and os.path.getsize(file_full_path) > 0:
        return 0, 0

    t0 = time.time()
    max_retries = 3
    tmp_path = file_full_path + ".tmp"

    def log(msg):
        if progress_slot is not None:
            progress_slot["progress"].print_line(msg)
        else:
            with print_lock:
                print(msg)

    for attempt in range(max_retries):
        try:
            if session:
                response = session.get(url, timeout=30, stream=True, headers={"Accept-Encoding": "identity"})
            else:
                response = requests.get(url, timeout=30, stream=True, headers={"Accept-Encoding": "identity"})
            response.raise_for_status()
            total_size = int(response.headers.get('Content-Length', 0))
            content_encoding = response.headers.get('Content-Encoding', '').strip().lower()
            start_time = time.time()
            downloaded_size = 0

            if progress_slot is not None:
                progress_slot["progress"].set_total(progress_slot["id"], total_size)

            os.makedirs(save_dir, exist_ok=True)

            # 先写入 .tmp 临时文件，全部下完且校验通过后再原子改名，
            # 避免截断/中断产生"存在但损坏"的正式文件被后续跳过。
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if progress_slot is not None:
                            progress_slot["progress"].update_file(progress_slot["id"], downloaded_size)
                        elif show_progress:
                            single_file_progress(downloaded_size, total_size, file_name, start_time)

            # 有 Content-Length 且响应未被压缩时严格校验完整性；不足即视为失败并重试。
            # 已请求 identity 编码，正常情况下 body 与 Content-Length 一致；
            # 若服务器仍压缩返回（Content-Encoding 非 identity），则无法用该长度校验。
            if total_size > 0 and content_encoding in ("", "identity") and downloaded_size != total_size:
                raise requests.exceptions.ChunkedEncodingError(
                    f"下载不完整：{downloaded_size}/{total_size} 字节"
                )
            if downloaded_size == 0:
                raise requests.exceptions.ChunkedEncodingError("下载内容为空")

            os.replace(tmp_path, file_full_path)
            return 0, time.time() - t0

        except requests.exceptions.RequestException as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

            if attempt < max_retries - 1:
                log(Fore.YELLOW + f"下载文件 {file_name} 失败，重试 {attempt+2}/{max_retries}，原因：{str(e)}")
                time.sleep(2 ** attempt)
            else:
                log(Fore.RED + f"下载文件 {file_name} 失败，原因：{str(e)}，URL：{url}")
                return 1, time.time() - t0
    return 1, time.time() - t0

PATCH_SKIP_NAMES = {"catalog_catalog.json", "catalog_catalog.hash"}
CATALOG_PLACEHOLDER = "http://rizastcdn.pigeongames.cn/default"


def parse_patch_metadata_text(text: str):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0].startswith("<?xml") or lines[0].startswith("<Error"):
        return None, []
    prev_version = lines[0]
    files = []
    for line in lines[1:]:
        if line.startswith("Android/") and line[len("Android/") :]:
            files.append(line)
    return prev_version, files


def getPatchMetadatas(serverVer: str, resourceBaseUrl: str):
    baseUrl = f"{resourceBaseUrl}/{serverVer}/patch_metadata"
    try:
        response = requests.get(baseUrl, timeout=30)
    except requests.exceptions.RequestException as e:
        print(Fore.RED + f"获取patchmetadata失败：{e} {baseUrl}")
        return None, []
    if response.status_code != 200:
        print(Fore.YELLOW + f"patch_metadata 已不可用（{response.status_code}），版本链在 {serverVer} 中断：{baseUrl}")
        return None, []
    prev_version, files = parse_patch_metadata_text(response.content.decode("utf-8", errors="replace"))
    if prev_version is None:
        print(Fore.YELLOW + f"patch_metadata 内容无效，版本链在 {serverVer} 中断")
        return None, []
    return prev_version, files

def readCataLog() -> list:
    with open("./download/catalog_catalog.json", "r", encoding="utf-8") as f:
        catalog = json.load(f)
    downList = []
    for item in catalog["m_InternalIds"]:
        if isinstance(item, str) and item.startswith("http"):
            downList.append(catalog_relative_path(item))
    return downList


def catalog_relative_path(internal_id: str) -> str:
    rel = internal_id
    if rel.startswith(CATALOG_PLACEHOLDER + "/"):
        rel = rel[len(CATALOG_PLACEHOLDER) + 1 :]
    elif rel.startswith(CATALOG_PLACEHOLDER):
        rel = rel[len(CATALOG_PLACEHOLDER) :].lstrip("/")
    if ".acb=" in rel and rel.endswith(".bundle"):
        rel = rel[: -len(".bundle")]
    return rel


def patch_lookup_keys(rel_path: str):
    keys = [rel_path]
    if rel_path.endswith(".bundle"):
        keys.append(rel_path[: -len(".bundle")])
    else:
        keys.append(rel_path + ".bundle")
    return keys


def resolve_file_version(rel_path: str, patch_map: dict, base_version: str):
    for key in patch_lookup_keys(rel_path):
        if key in patch_map:
            return patch_map[key]
    return base_version


def build_download_url(resource_base_url: str, version: str, rel_path: str) -> str:
    return f"{resource_base_url}/{version}/{rel_path}"


def _download_resolved_file(rel_path, patch_map, base_version, all_versions, resource_base_url, session, progress, slot_id):
    t0 = time.time()
    versions = []
    mapped = resolve_file_version(rel_path, patch_map, base_version)
    for ver in [mapped] + list(all_versions):
        if ver and ver not in versions:
            versions.append(ver)
    for ver in versions:
        url = build_download_url(resource_base_url, ver, rel_path)
        state, _ = downloadFile(url, session, show_progress=False, progress_slot={"progress": progress, "id": slot_id})
        if state == 0:
            return 0, time.time() - t0
    return 1, time.time() - t0

def clearDownload():
    download_path = "./download"
    if os.path.exists(download_path):
        shutil.rmtree(download_path)
    os.mkdir(download_path)
    levelInfoPath = "./output/default.json"
    if os.path.exists(levelInfoPath):
        os.remove(levelInfoPath)
    chartInfoPath = "./output/charts"
    if os.path.exists(chartInfoPath):
        shutil.rmtree(chartInfoPath)

def _make_session():
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _run_downloads(rel_paths, patch_map, base_version, all_versions, resource_base_url, label):
    file_count = len(rel_paths)
    if file_count == 0:
        print(Fore.GREEN + f"{label}无需下载")
        return
    failed = 0
    session = _make_session()
    progress = MultiProgress(total_files=file_count, slots=MAX_WORKERS)

    # 用队列预分配显示槽位，保证并发数 == 显示行数（最多 MAX_WORKERS 行）
    slot_queue = queue.Queue()
    for slot_id in range(MAX_WORKERS):
        slot_queue.put(slot_id)

    def worker(rel_path, name):
        slot_id = slot_queue.get()
        try:
            progress.start_file(slot_id, name)
            state, dt = _download_resolved_file(
                rel_path, patch_map, base_version, all_versions, resource_base_url, session, progress, slot_id
            )
            progress.finish_file(slot_id, state == 0)
            return state, dt
        finally:
            slot_queue.put(slot_id)

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            for rel_path in rel_paths:
                name = rel_path.split("/")[-1]
                futures[executor.submit(worker, rel_path, name)] = rel_path
            for future in as_completed(futures):
                state, dt = future.result()
                if state != 0:
                    failed += 1
    finally:
        progress.close()
    print(Fore.GREEN + f"{label}完成，成功 {file_count - failed}，失败 {failed}")


def collect_patch_chain(resource_base_url: str, current_ver: str):
    all_versions = [current_ver]
    patch_map = {}
    base_version = current_ver
    server_ver = current_ver
    while True:
        prev_version, files = getPatchMetadatas(server_ver, resource_base_url)
        if prev_version is None:
            print(Fore.GREEN + "已到达当前 CDN 上仍保留的热更新终点")
            break
        resource_count = 0
        for item in files:
            name = item[len("Android/") :]
            if name in PATCH_SKIP_NAMES:
                continue
            resource_count += 1
            if item not in patch_map:
                patch_map[item] = server_ver
        print(Fore.CYAN + f"{server_ver} 热更新 Android 资源：{resource_count} 个（上一版本 {prev_version}）")
        base_version = prev_version
        if prev_version in all_versions:
            break
        all_versions.append(prev_version)
        server_ver = prev_version
    return all_versions, patch_map, base_version


def collect_download_list(catalog_files, patch_map):
    seen = set()
    ordered = []
    for rel_path in catalog_files:
        if rel_path not in seen:
            seen.add(rel_path)
            ordered.append(rel_path)
    for item in patch_map:
        name = item[len("Android/") :] if item.startswith("Android/") else item
        if name in PATCH_SKIP_NAMES:
            continue
        if item not in seen and name not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def main():
    inputStr = input(Fore.YELLOW + "是否清空下载目录？(y/n)")
    if inputStr.lower() != "y" and inputStr.lower() != "yes":
        print(Fore.GREEN + "取消清空")
    else:
        clearDownload()
        print(Fore.GREEN + "清空下载目录完成")
    rizlineVer = getRizlineVersion()
    serverVer = rizlineVer["resourceVersion"]
    resourceBaseUrl = rizlineVer["resourceBaseUrl"]
    print(resourceBaseUrl + f"/{serverVer}/Android/catalog_catalog.json")
    downloadFile(resourceBaseUrl + f"/{serverVer}/Android/catalog_catalog.json")
    catalog_files = readCataLog()
    allServerVer, patch_map, base_version = collect_patch_chain(resourceBaseUrl, serverVer)
    print(Fore.GREEN + f"全部版本号：{allServerVer}")
    print(Fore.GREEN + f"基线目录 resourceBaseVersion：{base_version}")
    print(Fore.GREEN + f"热更映射 {len(patch_map)} 条，catalog 远程 {len(catalog_files)} 条")
    download_list = collect_download_list(catalog_files, patch_map)
    print(Fore.GREEN + f"共需下载 {len(download_list)} 个远程文件（含热更与基线）")
    inputStr = input(Fore.YELLOW + "是否开始下载全部远程资源？(y/n)")
    if inputStr.lower() != "y" and inputStr.lower() != "yes":
        print(Fore.RED + "取消下载")
    else:
        _run_downloads(download_list, patch_map, base_version, allServerVer, resourceBaseUrl, "下载")
    parse_level()
    if os.path.exists("./output/default.json"):
        print(Fore.GREEN + "导出关卡信息文件成功")
    else:
        print(Fore.RED + "导出关卡信息文件失败")
        return
    parse_catalog()
    export_all_resources()
    input(Fore.YELLOW + "按任意键退出")

main()
