# 获取Rizline的资源文件


通过抓包得到鸽游服务器的下载api，再利用游戏安装包的catalog.json的文件列表，即可实现下载资源

对于.acb的音频文件，需要用到vgmstream-cli转换成wav

https://github.com/vgmstream/vgmstream

https://github.com/Virace/vgmstream-cli-build(本项目使用)

当前脚本已支持:

1.自动从服务器更新catalog.json

2.解析catalog并下载文件

3.解析catalog里面的bundle文件名

4.从bundle提取游戏资源（谱面，曲绘，音频等）

5.对现有资源进行分类，自动转换acb2wav

20260702：自今日起该项目可能会用到ai辅助编程，下载功能已改为多线程下载，并修复了一些存在问题 by CHCAT1320

QQ:1095216448

# Rizline Resource File Acquisition


By packet capturing the download API of Pigeon Games' server, and utilizing the file list from the game's catalog.json in the installation package, resource downloading can be achieved.

For .acb audio files, vgmstream-cli is required to convert them to wav format.

https://github.com/vgmstream/vgmstream

https://github.com/Virace/vgmstream-cli-build((This project uses)

Current script features:

1. Automatic catalog.json updates from the server

2. Parsing catalog and downloading files

3. Parsing bundle filenames within the catalog

4. Extracting game resources from bundles (charts, illustrations, audio, etc.)

5. Categorizing existing resources and automatic acb2wav conversion

20260702: From today onwards, this project may utilize AI-assisted programming. The download function has been changed to multi-threaded downloading, and several existing issues have been fixed. by CHCAT1320

QQ: 1095216448
