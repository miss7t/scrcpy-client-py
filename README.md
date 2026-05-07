PyScrcpy



Python 客户端 for scrcpy 3.3.4 — 截图、触控、按键自动化接口。



⚠️ 本项目代码由 AI 生成，未经全面测试



安装

----

pip install av numpy

\# 可选：保存截图需 Pillow，显示窗口需 pygame

pip install Pillow pygame



系统要求：

\- Android SDK Platform Tools（确保 adb 在 PATH 中）

\- 设备已开启 USB 调试并已授权



获取 scrcpy-server

------------------

本项目固定使用 scrcpy v3.3.4，请手动下载对应的 server 文件：

1\. 前往 https://github.com/Genymobile/scrcpy/releases 下载 v3.3.4 的 scrcpy-server-v3.3.4

2\. 将文件放到 scrcpy\_device 包目录，或你运行脚本的根目录

注意：server jar 不包含在本仓库中，请自行获取。



快速开始

--------

from scrcpy\_device import ScrcpyClient



\# 自动连接第一个设备

with ScrcpyClient() as client:

&nbsp;   client.tap(100, 200)

&nbsp;   img = client.get\_frame()          # 阻塞获取新帧



指定设备序列号：

client = ScrcpyClient(serial="abcd1234")

client.connect()

\# 进行操作...

client.disconnect()



主要功能

--------

视频帧     get\_frame(timeout) 阻塞新帧

&nbsp;          last\_frame 非阻塞最新帧

触控       tap(x, y)

&nbsp;          swipe(x1,y1,x2,y2, duration)

&nbsp;          long\_press(x,y,duration)

&nbsp;          低阶 touch\_down/up/move

系统按键   home(), back(), recent\_apps(), power(), volume\_up() 等

系统控制   start\_app(package), screen\_on/off, rotate\_device()

&nbsp;          通知面板展开/收起

&nbsp;          剪贴板读写（异步回调）

回调       on\_clipboard(cb), on\_clipboard\_ack(cb), on\_disconnect(cb)



详细接口请查看 api.py 中的 ScrcpyClient 类。



配置参数

--------

可在构造 ScrcpyClient 时传入：

ScrcpyClient(

&nbsp;   serial="...",         # 设备序列号，不填则自动选第一个

&nbsp;   max\_size=0,           # 0=原始分辨率，>0 限制最大边长

&nbsp;   bitrate=8\_000\_000,    # 视频码率

&nbsp;   max\_fps=30,           # 0=不限制

&nbsp;   video\_codec="h264",   # h264 / hevc / av1

&nbsp;   stay\_awake=True,      # 保持设备唤醒

&nbsp;   lock\_orientation=-1,  # -1=不锁定，0~3 对应 0°,90°,180°,270°

&nbsp;   control\_enabled=True  # 是否开启控制通道

)



常见问题

--------

设备未找到？

检查 adb devices 是否列出设备；确认 USB 调试授权。

server jar 未找到？

确认文件已下载并放置于 scrcpy\_device/ 或运行目录。

控制无效？

确保设备已解锁屏幕，且未在其他 scrcpy 会话中占用控制权。



许可证

------

MIT License © 2025 \[miss7t]

本项目基于 Genymobile/scrcpy 协议实现。

