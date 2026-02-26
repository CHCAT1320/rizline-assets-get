import requests
import json
import os
import base64
import shutil
import struct
import UnityPy
import time
import subprocess
import platform

from colorama import init, Fore, Back, Style
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


# 下载单个文件 ==> 保存到本地
def downloadFile(url: str) -> int:
    root_download_dir = "./download"
    file_name = url.split("/")[-1]
    save_dir = root_download_dir
    
    # 分类保存 ==> bundles、acb ==> ./download/bundles、./download/acb
    if url.endswith("bundle"):
        save_dir = os.path.join(root_download_dir, "bundles")
    elif ".acb=" in url:
        save_dir = os.path.join(root_download_dir.split("=")[0], "acb")
        acbId = file_name.split(".acb=")[1]
        file_name = file_name.split(".acb=")[0]
        if len(file_name.split(".")) < 3:
            file_name = file_name.split(".")[0] + "." + acbId + "." + file_name.split(".")[1] + ".acb"
        else:
            file_name = file_name.split(".")[0] + "." + acbId + "." + file_name.split(".")[1] + "." + file_name.split(".")[2] + ".acb"

    file_full_path = os.path.join(save_dir, file_name)
    
    # 如果文件存在 ==> 跳过 ==> 且不是catalog文件 ==> 则直接返回
    if os.path.exists(file_full_path) and not file_name.endswith("catalog_catalog.json"):
        return 0

    try:
        # 尝试下载文件 retrn 0 ==> 成功 1 ==> 失败
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('Content-Length', 0))
        start_time = time.time()
        downloaded_size = 0
        
        os.makedirs(save_dir, exist_ok=True)
        
        with open(file_full_path, "wb") as f:
            # iter_content按指定块大小迭代读取，实现流式下载
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:  # 过滤空块（部分服务器会返回空字节块）
                    f.write(chunk)  # 逐块写入本地文件
                    downloaded_size += len(chunk)  # 累计已下载字节数
                    # 每下载一块刷新一次进度条，实现实时更新
                    single_file_progress(downloaded_size, total_size, file_name, start_time)
            print()
        return 0

    except requests.exceptions.RequestException as e:
        # 下载失败 ==> 打印错误信息
        err_info = f"下载文件 {file_name} 失败，原因：{str(e)}，URL：{url}"
        print(Fore.RED + err_info)
        return 1

# 通过循环获取patchmetadata ==> 获取每个版本更新的内容
def getPatchMetadatas(serverVer: str) -> list:
    baseUrl = f"https://rizlineasset.pigeongames.net/versions/{serverVer}/patch_metadata"
    response = requests.get(baseUrl)
    if response.status_code == 200:
        patchMetadatas = response.text
        return patchMetadatas.split("\n")
    else:
        if serverVer == "v100_2_0_8_86e2fda4e0":
            print(Fore.GREEN + "获取所有patchmetadata完成")
            return None
        print(Fore.RED + "获取patchmetadata失败" + str(response.status_code) + baseUrl)
        return None

def readCataLog() -> list:
    with open("./download/catalog_catalog.json", "r", encoding="utf-8") as f:
        catalog = json.load(f)
    downList = []
    for item in catalog["m_InternalIds"]:
        if item.startswith("http"):
            if ".acb=" in item:
                item = item.split(".bundle")[0]
            downList.append(item)
    return downList

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

def parse_unity_catalog(catalog):
    # base64解码为二进制字节数组
    def b642bytes(s):
        return bytearray(base64.b64decode(s))

    # 字节读取器-小端序专用
    class ByteReader:
        __slots__ = ['data', 'pos']
        def __init__(self, data):
            self.data = data
            self.pos = 0
        def read(self, ln):
            res = self.data[self.pos:self.pos+ln]
            self.pos += ln
            return res
        def read_int32(self):
            return struct.unpack('<i', self.read(4))[0]

    # 解码三大核心二进制流
    key_bytes = b642bytes(catalog['m_KeyDataString'])
    bucket_bytes = b642bytes(catalog['m_BucketDataString'])
    entry_bytes = b642bytes(catalog['m_EntryDataString'])

    reader = ByteReader(bucket_bytes)
    bucket_count = reader.read_int32()
    table = []

    for _ in range(bucket_count):
        key_pos = reader.read_int32()
        key_type = key_bytes[key_pos] if key_pos < len(key_bytes) else -1
        curr_kp = key_pos + 1
        key_val = None

        # 解析UTF8/UTF16字符串Key | 数字Key
        if key_type in (0, 1):
            str_len = key_bytes[curr_kp] if curr_kp < len(key_bytes) else 0
            curr_kp +=4
            s_byte = key_bytes[curr_kp : curr_kp+str_len]
            if key_type == 0:
                key_val = bytes(s_byte).decode('utf-8', errors='ignore') # UTF8中文
            else:
                key_val = bytes(s_byte).decode('utf-16-le', errors='ignore') # UTF16小端中文
        elif key_type == 4:
            key_val = key_bytes[curr_kp] if curr_kp < len(key_bytes) else 0

        # 解析Entry数据
        entry_val = 65535
        entry_count = reader.read_int32()
        for _ in range(entry_count):
            entry_pos = reader.read_int32()
            entry_start = 4 + 28 * entry_pos
            e_byte = entry_bytes[entry_start+8 : entry_start+10]
            entry_val = struct.unpack('<H', bytes(e_byte))[0] if len(e_byte)==2 else 65535
        
        table.append([key_val, entry_val])

    # 处理引用关联 替换索引为真实名称
    for i in range(len(table)):
        val = table[i][1]
        if val != 65535 and 0 <= val < len(table):
            table[i][1] = table[val][0]

    return table

# 解析catalog的m_KeyDataString ==> 获取bundle文件名列表
def parseCatalog() -> list:
    with open("./download/catalog_catalog.json", "r", encoding="utf-8") as f:
        catalog = json.load(f)
    keyData = parse_unity_catalog(catalog)
    with open("./download/fileList.json", "w", encoding="utf-8") as f:
        json.dump(keyData, f, indent=4, ensure_ascii=False, separators=(',', ': '))
    return keyData


# 解析、解包bundle文件 ==> 导出关卡信息文件
def parseLevel():
    # 先查找每个bundle ==> 找到关卡信息
    for path in os.listdir("./download/bundles"):
        bundle = UnityPy.load(os.path.join("./download/bundles", path))
        for obj in bundle.objects:
            data = obj.read()
            
            if obj.type.name == "MonoBehaviour" and data.m_Name == "Default":
                data = obj.read_typetree()
                with open("./output/default.json" , "w", encoding="utf-8") as f:
                    formatted_data = json.dumps(
                    data,
                    indent=4,
                    ensure_ascii=False,
                    separators=(',', ':'),
                    )
                    f.write(formatted_data)
                break

# parseLevel(parseCatalog())

def outputBundle():
    with open("./download/fileList.json", "r", encoding="utf-8") as f:
        fileList = json.load(f)
    with open("./output/default.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        levels = data["levels"]
    i = 1
    for level in levels:
        # 获取谱面名称和所在类别
        levelId = level["id"]
        name = levelId.split('.')[0]
        discName = level["discName"]
        chartIds = level["chartIds"]
        illustrationId = level["illustrationId"]
        musicId = level["musicId"]
        if not os.path.exists(f"output/charts/{discName}"):
            os.makedirs(f"output/charts/{discName}")
        # if os.path.exists(f"./output/charts/{discName}/{name}"):
        #     print(Fore.RED + f"导出进度：{i}/{len(levels)} {Fore.CYAN}{name} {Fore.RED}失败，已存在相同关卡，为避免重复导出，跳过此关卡")
        #     i += 1
        #     continue
        if not os.path.exists(f"output/charts/{discName}/{name}"):
            os.makedirs(f"output/charts/{discName}/{name}")
        # 遍历chartIds ==> 找到对应谱面文件 ==> 导出到本地
        # 导出谱面文件 ==> charts/discXX/levelXX/chartId.json
        for chartId in chartIds:
            for file in fileList:
                if file[0] == chartId:
                    bundle = UnityPy.load(os.path.join("./download/bundles", file[1]))
                    for obj in bundle.objects:
                        if obj.type.name == "TextAsset":
                            chartData = obj.read()
                            with open(f"output/charts/{discName}/{name}/{chartId}.json", "wb") as f:
                                f.write(chartData.m_Script.encode("utf-8"))
        # 导出曲绘文件 ==> charts/discXX/levelXX/illustrationId.png
        for file in fileList:
            if file[0] == illustrationId:
                bundle = UnityPy.load(os.path.join("./download/bundles", file[1]))
                for obj in bundle.objects:
                    if obj.type.name in ["Texture2D", "Sprite"]:
                        imgData = obj.read()
                        path = os.path.join(f"output/charts/{discName}/{name}", illustrationId + ".png")
                        imgData.image.save(path)
        # 转换音频文件格式 ==> acb2wav ==> charts/discXX/levelXX/musicId.wav
        system = platform.system()
        if system == "Windows":
            vgcPath = "./vgmstream-cli/vgmstream-cli.exe"
        else:  # Linux 或 macOS
            # 优先检查本地目录
            local_path = "./vgmstream-cli/vgmstream-cli"
            if os.path.exists(local_path):
                vgcPath = local_path
            else:
                # 尝试从系统 PATH 中查找（如果已全局安装）
                vgcPath = "vgmstream-cli"  # Linux 通常直接调用命令名
                if not shutil.which(vgcPath):
                    raise FileNotFoundError("未找到 vgmstream-cli，请确保已安装或在 ./vgmstream-cli/ 目录下")

        acbPath = "./download/acb/"
        for file in os.listdir(acbPath):
            if name.lower() == file.split(".")[0]:
                # 确保输出目录存在
                output_dir = f"output/charts/{discName}/{name}"
                os.makedirs(output_dir, exist_ok=True)
                
                subprocess.run([
                    vgcPath,
                    "-o", os.path.join(output_dir, musicId + ".wav"),
                    os.path.join(acbPath, file),
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 导出关卡信息文件 ==> charts/discXX/chartInfojson
        with open(f"output/charts/{discName}/{name}/chartInfo.json", "w", encoding="utf-8") as f:
            allChartsList = data["charts"]
            chartLevel = []
            for chart in allChartsList:
                if chart["id"] in chartIds:
                    difficultyLevel = chart["level"]
                    difficulty = chart["difficulty"]
                    designer = chart["designer"]
                    chartLevel.append({
                        "difficultyLevel": difficultyLevel,
                        "difficulty": difficulty,
                        "designer": designer,
                    })
            chartInfo = {
                "name": name,
                "levelId": levelId,
                "discName": discName,
                "chartIds": chartIds,
                "illustrationId": illustrationId,
                "musicId": musicId,
                "appearType": level["appearType"],
                "seriesIndex": level["seriesIndex"],
                "isNewLevel": level["isNewLevel"],
                "chartLevel": chartLevel,
            }
            f.write(json.dumps(chartInfo, indent=4, ensure_ascii=False, separators=(',', ':')))

        print(f"{Fore.GREEN}导出进度：{Fore.YELLOW}{i}/{len(levels)} {Fore.CYAN}{name} {Fore.GREEN}成功")
        i += 1

#outputBundle()

def main():
    # 清空下载目录
    inputStr = input(Fore.YELLOW + "是否清空下载目录？(y/n)")
    if inputStr.lower() != "y" and inputStr.lower() != "yes":
        print(Fore.GREEN + "取消清空")
    else:
        clearDownload()
        print(Fore.GREEN + "清空下载目录完成")
    # 获取Rizline版本号
    rizlineVer = getRizlineVersion()
    serverVer = rizlineVer["resourceVersion"]
    allServerVer = [serverVer]
    allUpdateFile = {}
    # 下载最早的版本号的catalog.json
    # downloadFile(rizlineVer["resourceBaseUrl"] + "/v100_2_0_8_86e2fda4e0/Android/catalog_catalog.json")
    print(rizlineVer["resourceBaseUrl"] + f"/{serverVer}/Android/catalog_catalog.json")
    downloadFile(rizlineVer["resourceBaseUrl"] + f"/{serverVer}/Android/catalog_catalog.json")
    allFile = readCataLog()
    while True:
        data = getPatchMetadatas(serverVer)
        if data == None:
            break
        allUpdateFile[serverVer] = []
        for item in data:
            if item.startswith("Android/") and item.endswith(".bundle"):
                allUpdateFile[serverVer].append(item)
        serverVer = data[0]
        allServerVer.append(serverVer)
    # print(Fore.GREEN + str(allServerVer))
    # print(Fore.GREEN + str(allUpdateFile))
    # 计算文件数量
    fileCount = 0
    for serverVer in allServerVer:
        if serverVer not in allUpdateFile:
            continue
        fileCount += len(allUpdateFile[serverVer])
    print(Fore.GREEN + f"共需下载{fileCount}个文件")
    # 询问是否开始下载
    inputStr = input(Fore.YELLOW + "是否开始下载热更新版本文件？(y/n)")
    if inputStr.lower() != "y" and inputStr.lower() != "yes":
        print(Fore.RED + "取消下载")
    else:
        # 下载更新文件
        i = 1
        for serverVer in allServerVer:
            if serverVer not in allUpdateFile:
                continue
            for item in allUpdateFile[serverVer]:
                state = downloadFile(rizlineVer["resourceBaseUrl"] + "/" + serverVer + "/" + item)
                if state == 0:
                    print(Fore.GREEN + f"下载进度：{i}/{fileCount} {item} 成功")
                i += 1
        print(Fore.GREEN + "下载完成")
        # 导出关卡信息文件
        print(Fore.GREEN + "解析关卡信息文件")
        parseLevel()
        if os.path.exists("./output/default.json"):
            print(Fore.GREEN + "导出关卡信息文件成功")
        else:
            print(Fore.RED + "导出关卡信息文件失败")
    fileCount = len(allFile)
    print(Fore.GREEN + f"共需下载{fileCount}个文件")
    # 询问是否开始下载
    inputStr = input(Fore.YELLOW + "是否开始下载基础文件？(y/n)")
    if inputStr.lower() != "y" and inputStr.lower() != "yes":
        print(Fore.RED + "取消下载")
    else:
        i = 1
        for file in allFile:
            file = file.replace("http://rizastcdn.pigeongames.cn/default", rizlineVer["resourceBaseUrl"] + "/" + allServerVer[len(allServerVer) - 1])
            state = downloadFile(file)
            if state == 0:
                print(Fore.GREEN + f"下载进度：{i}/{fileCount} {file} 成功")
            else:
                for ver in allServerVer :
                    print(Fore.RED + f"下载进度：{i}/{fileCount} {file} 失败，尝试备用版本" + ver)
                    file = file.replace("http://rizastcdn.pigeongames.cn/default", rizlineVer["resourceBaseUrl"] + "/" + ver)
                    state = downloadFile(file)
                    if state == 0:
                        print(Fore.GREEN + f"下载进度：{i}/{fileCount} {file} 成功")
                        break
                if state != 0:
                    print(Fore.RED + f"下载进度：{i}/{fileCount} {file} 失败")
            i += 1
        print(Fore.GREEN + "下载完成")
    # 导出关卡信息文件
    if not os.path.exists("./output/default.json"):
        parseLevel()
    if os.path.exists("./output/default.json"):
        print(Fore.GREEN + "导出关卡信息文件成功")
    else:
        print(Fore.RED + "导出关卡信息文件失败")
        return
    parseCatalog()
    outputBundle()
    input(Fore.YELLOW + "按任意键退出")

main()