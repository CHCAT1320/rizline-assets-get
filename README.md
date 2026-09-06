# 获取Rizline的资源文件


通过抓包得到鸽游服务器的下载api，再利用游戏安装包的catalog.json的文件列表，即可实现下载资源

对于.acb的音频文件，需要用到vgmstream-cli转换成wav

https://github.com/vgmstream/vgmstream

https://github.com/Virace/vgmstream-cli-build (本项目使用)

当前脚本已支持:

1.自动从服务器更新catalog.json

2.按 patch_metadata 热更链解析版本，热更走 resourcePatchMap，基线走 resourceBaseVersion

3.下载 catalog 全部远程 bundle / acb（acb 去掉末尾 .bundle，保留 cridata 路径）

4.解析 catalog 的 bundle 映射，自动选择最新关卡信息文件

5.分类解包：谱面（含 .mr / .cn / challenge）、曲绘（含 HiRes）、layout、系列海报/横幅、头像、本地化、视频、UI、音频 acb2wav

6.解包逻辑与下载解耦，资源覆盖重写

20260702：自今日起该项目可能会用到ai辅助编程，下载功能已改为多线程下载，并修复了一些存在问题 by CHCAT1320

QQ:1095216448

# Rizline Resource File Acquisition


By packet capturing the download API of Pigeon Games' server, and utilizing the file list from the game's catalog.json in the installation package, resource downloading can be achieved.

For .acb audio files, vgmstream-cli is required to convert them to wav format.

https://github.com/vgmstream/vgmstream

https://github.com/Virace/vgmstream-cli-build (This project uses)

Current script features:

1. Automatic catalog.json updates from the server

2. Walk the patch_metadata chain; patched files use resourcePatchMap, baseline files use resourceBaseVersion

3. Download all remote catalog bundles / acb (strip trailing .bundle from acb URLs, keep cridata paths)

4. Parse catalog bundle mappings and auto-select the latest level info file

5. Typed unpack: charts (including .mr / .cn / challenge), illustrations (including HiRes), layouts, series posters/banners, avatars, localization, videos, UI, and acb2wav

6. Unpack is decoupled from download; existing files are overwritten

20260702: From today onwards, this project may utilize AI-assisted programming. The download function has been changed to multi-threaded downloading, and several existing issues have been fixed. by CHCAT1320

QQ: 1095216448
