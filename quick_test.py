#!/usr/bin/env python3
"""极简测试：连接 → 等待首帧 → 截图 → 点击 → Home → 截图 → 断开"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scrcpy_device2 import ScrcpyClient, ConnectionError, FrameTimeoutError

SERIAL = "手动输入序列号"
client = ScrcpyClient(serial=SERIAL)

print("1. 连接设备...")
try:
    client.connect()
    print(f"   成功: {client.device_name}, {client.resolution}")
except ConnectionError as e:
    print(f"   失败: {e}"); exit(1)

print("2. 等待首帧...")
try:
    client.wait_for_frame(timeout=10)
    print("   首帧已到达")
except FrameTimeoutError:
    print("   超时，但尝试继续...")

print("3. 截图...")
try:
    frame = client.get_frame(timeout=5)
    print(f"   截图成功，尺寸: {frame.shape}")
    # 保存
    from PIL import Image
    Image.fromarray(frame).save("quick_screenshot.png")
    print("   已保存 quick_screenshot.png")
except Exception as e:
    print(f"   截图失败: {e}")

print("4. 点击屏幕中心...")
try:
    w, h = client.resolution
    client.tap(w//2, h//2)
    print("   点击完成")
    time.sleep(0.5)
except Exception as e:
    print(f"   点击失败: {e}")

print("5. 按 Home 键...")
try:
    client.home()
    print("   Home 已发送")
    time.sleep(1.0)
except Exception as e:
    print(f"   Home 失败: {e}")

print("6. 再次截图（操作后）...")
try:
    frame2 = client.get_frame(timeout=5)
    Image.fromarray(frame2).save("after_actions.png")
    print("   已保存 after_actions.png")
except Exception as e:
    print(f"   再次截图失败: {e}")

print("7. 断开连接...")
client.disconnect()
print("   测试完成，退出")