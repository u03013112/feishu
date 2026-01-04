import lark_oapi as lark
from lark_oapi.api.im.v1 import *
import logging
import sys
import os
import json
import re
import pyperclip
import subprocess

# 将当前目录加入路径，确保能导入同级模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import config
except ImportError:
    print("【错误】找不到 src/config.py 配置文件。")
    sys.exit(1)

# 设置日志级别
logging.basicConfig(level=logging.INFO)

import threading
from collections import deque
# 全局去重缓存
processed_msg_ids = deque(maxlen=100)

APP_ID = config.APP_ID
APP_SECRET = config.APP_SECRET

def play_sound_task(text):
    try:
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"])
        subprocess.run(["say", text])
    except Exception as e:
        print(f"音频播放失败: {e}")

def say_notification(text):
    """启动后台线程播放"""
    threading.Thread(target=play_sound_task, args=(text,)).start()

def extract_verification_code(content_json):
    """
    从消息内容中提取验证码
    预期格式：... entering the verification code below. The code will expire soon. RHV-49A If you didn’t request ...
    验证码特征：大写字母+数字+连字符，例如 RHV-49A
    """
    try:
        # 解析 JSON 字符串
        data = json.loads(content_json)
        
        # 提取所有文本元素
        full_text = ""
        
        # 处理卡片消息 (interactive) 的结构
        # 结构通常是: elements -> [[{"tag":"text", "text":"..."}]]
        if "elements" in data:
            for row in data["elements"]:
                for item in row:
                    if item.get("tag") == "text":
                        full_text += item.get("text", "") + " "
        
        # 如果是普通文本消息，可能直接在 text 字段
        if "text" in data:
            full_text += data["text"]

        print(f"[调试] 提取到的完整文本: {full_text[:100]}...") # 打印前100字符调试

        # 使用正则提取验证码
        # 模式：XXX-XXX 或类似的格式
        # 根据日志样本: "RHV-49A"
        # 匹配规则：3-4个大写字母 + 连字符 + 2-4个数字/字母
        # 也可以放宽一点： [A-Z0-9]{3}-[A-Z0-9]{3}
        match = re.search(r'\b[A-Z0-9]{3,4}-[A-Z0-9]{3,4}\b', full_text)
        
        if match:
            return match.group(0)
        
        return None

    except json.JSONDecodeError:
        print("消息内容不是有效的 JSON")
        return None
    except Exception as e:
        print(f"提取过程出错: {e}")
        return None

def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    event = data.event
    message = event.message
    
    # 消息去重
    msg_id = message.message_id
    if msg_id in processed_msg_ids:
        print(f"[重复消息] 已跳过: {msg_id}")
        return
    processed_msg_ids.append(msg_id)
    content = message.content
    msg_type = message.message_type
    
    print(f"\n[收到消息] 类型: {msg_type}")

    # 仅处理 interactive (卡片消息) 或 text (文本消息)
    if msg_type == "interactive" or msg_type == "text":
        code = extract_verification_code(content)
        
        if code:
            print(f"✅ 找到验证码: {code}")
            
            # 1. 复制到剪贴板
            try:
                pyperclip.copy(code)
                print("📋 已复制到剪贴板")
            except Exception as e:
                print(f"❌ 剪贴板操作失败: {e}")

            # 2. 语音播报
            say_notification(f"收到验证码 {code}")
            
        else:
            print("未在消息中找到符合格式的验证码")
    else:
        print("跳过非文本/卡片消息")

def main():
    if APP_ID == "您的AppID":
        print("请配置 config.py")
        return

    print(f"正在启动验证码监听助手 (AppID: {APP_ID})...")
    print("等待 Databricks 验证邮件消息...")

    ws_client = lark.ws.Client(
        APP_ID, 
        APP_SECRET, 
        event_handler=lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
            .build(),
        log_level=lark.LogLevel.INFO
    )

    ws_client.start()

if __name__ == "__main__":
    main()
