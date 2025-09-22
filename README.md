# 获取Rizline的资源文件

目前官方态度不明暂不公开具体方法及脚本

通过抓包得到鸽游服务器的下载api，再利用游戏安装包的catalog.json的文件列表，即可实现下载资源

对于.acb的音频文件，需要用到vgmstream-cli转换成wav

当前脚本已支持:

1.自动从服务器更新catalog.json

2.解析catalog并下载文件

3.解析catalog里面的bundle文件名

4.从bundle提取游戏资源（谱面，曲绘，音频，rizcard等）

5.对现有资源进行分类，自动转换acb2wav

QQ:1095216448（请不要尝试从此渠道获取，因为我不会给）