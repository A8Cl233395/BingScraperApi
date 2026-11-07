#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mock WebSocket Client for /link
用于测试和模拟连接到 Web Search API 后端 /link 端点的 WebSocket 客户端。
支持接收服务端全双工推送（记忆增删/同步），并提供交互式控制台进行主动数据操作。

使用方法:
    python mock_websocket_client.py [127.0.0.1:5212/link]
    缺省参数时使用默认值: 127.0.0.1:5212/link
"""

import argparse
import asyncio
import datetime
import inspect
import json
import os
import re
import sys
import threading
import urllib.parse
from typing import Any, Dict, Optional

try:
    import websockets
except ImportError:
    print("错误: 未检测到 websockets 库，请使用 pip install websockets 安装。")
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None


# ============================== 终端彩色输出辅助 ==============================

def check_use_color() -> bool:
    """检查当前终端是否适合启用 ANSI 颜色代码"""
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        # 启用 Windows 控制台虚拟终端转义字符序列支持
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass
        return True
    return os.environ.get("TERM") != "dumb"

USE_COLOR = check_use_color()

def _color(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text

def color_info(text: str) -> str:
    return _color("36", text)  # 青色

def color_success(text: str) -> str:
    return _color("32", text)  # 绿色

def color_warn(text: str) -> str:
    return _color("33", text)  # 黄色

def color_error(text: str) -> str:
    return _color("31", text)  # 红色

def color_dim(text: str) -> str:
    return _color("90", text)  # 暗灰

def color_bold(text: str) -> str:
    return _color("1", text)   # 粗体


def log_msg(tag: str, msg: str, color_fn=color_info):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    timestamp = color_dim(f"[{now}]")
    prefix = color_fn(f"[{tag}]")
    print(f"{timestamp} {prefix} {msg}", flush=True)


# ============================== 配置与工具函数 ==============================

def normalize_ws_url(target: str) -> str:
    """
    规范化目标地址为合法 websocket URL。
    支持输入例如:
        127.0.0.1:5212/link  -> ws://127.0.0.1:5212/link
        127.0.0.1:5212       -> ws://127.0.0.1:5212/link
        http://localhost:5212 -> ws://localhost:5212/link
        https://example.com/link -> wss://example.com/link
        ws://127.0.0.1:5212/link -> ws://127.0.0.1:5212/link
    """
    target = (target or "").strip()
    if not target:
        target = "127.0.0.1:5212/link"

    if target.startswith("http://"):
        target = "ws://" + target[7:]
    elif target.startswith("https://"):
        target = "wss://" + target[8:]
    elif not (target.startswith("ws://") or target.startswith("wss://")):
        target = "ws://" + target

    parsed = urllib.parse.urlsplit(target)
    path = parsed.path
    if not path or path == "/":
        path = "/link"

    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def find_auth_key(specified_key: Optional[str] = None) -> str:
    """
    自动查找服务端的 auth_key:
    1. 命令行参数直接指定
    2. 环境变量 LINK_KEY 或 AUTH_KEY
    3. 当前及上层目录的 config.yaml / config.yml
    """
    if specified_key and specified_key.strip():
        return specified_key.strip()

    env_key = os.environ.get("LINK_KEY") or os.environ.get("AUTH_KEY")
    if env_key and env_key.strip():
        return env_key.strip()

    if yaml:
        search_paths = [
            "config.yaml",
            "config.yml",
            os.path.join(os.path.dirname(__file__), "config.yaml"),
            os.path.join(os.path.dirname(__file__), "config.yml"),
        ]
        for cfg_path in search_paths:
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        key = data.get("server", {}).get("auth_key")
                        if key:
                            return str(key).strip()
                except Exception:
                    pass

    return ""


def get_ws_connect_kwargs(key: str) -> Dict[str, Any]:
    """
    自适应 websockets 库版本构造请求头参数。
    websockets >= 14 使用 additional_headers，旧版本使用 extra_headers。
    """
    headers = {"key": key}
    sig = inspect.signature(websockets.connect)
    if "additional_headers" in sig.parameters:
        return {"additional_headers": headers}
    return {"extra_headers": headers}


# ============================== 客户端实现 ==============================

class MockWebSocketClient:
    def __init__(self, target_url: str, auth_key: str, default_user_id: int = 1):
        self.raw_target = target_url
        self.ws_url = normalize_ws_url(target_url)
        self.auth_key = auth_key
        self.default_user_id = default_user_id

        self.ws: Optional[Any] = None
        self.is_connected = False
        self.running = True
        self.reconnect_requested = asyncio.Event()

    def print_banner(self):
        masked_key = self.auth_key[:2] + "****" + self.auth_key[-2:] if len(self.auth_key) >= 4 else "****"
        print(color_bold("=" * 64))
        print(color_bold("   Web Search API - Link Mock WebSocket Client"))
        print(color_bold("=" * 64))
        print(f" • 目标地址:   {color_info(self.ws_url)}")
        print(f" • 鉴权 Key:   {color_warn(masked_key or '(未配置)')}")
        print(f" • 默认用户:   {color_success(str(self.default_user_id))}")
        print(f" • 交互提示:   输入 {color_bold('help')} 或 {color_bold('?')} 查看所有可用命令")
        print(color_bold("=" * 64) + "\n")

    def print_help(self):
        print(f"""
{color_bold("可用命令列表:")}
  {color_info("add [uid] <内容>")}     添加一条记忆 (例如: add 喜欢下棋 / add 2 喜欢看书)
  {color_info("del [uid] <内容>")}     删除一条记忆 (别名: rm, remove)
  {color_info("pull [uid]")}          从服务端拉取用户全量记忆 (pull_all)
  {color_info("push [uid] <m1,m2>")}  全量推送记忆至服务端，逗号分隔 (push_all)
  {color_info("raw <JSON字符串>")}    直接发送一段原始 JSON 数据
  {color_info("<直接输入JSON>")}      以 {{ 开头的合法 JSON 字符串会自动被直接发送
  {color_info("user [uid]")}          查看或切换当前默认操作的 UID (当前: {self.default_user_id})
  {color_info("status")}              查看当前连接状态及配置信息
  {color_info("reconnect")}           立即重新发起 WebSocket 连接
  {color_info("clear")}               清屏
  {color_info("help / ?")}            显示此帮助信息
  {color_info("exit / quit / q")}     断开连接并退出客户端
""")

    async def send_json(self, payload: dict) -> bool:
        """发送 JSON 消息至服务端"""
        if not self.ws or not self.is_connected:
            log_msg("错误", "WebSocket 未连接，无法发送消息", color_error)
            return False
        try:
            raw_text = json.dumps(payload, ensure_ascii=False)
            await self.ws.send(raw_text)
            log_msg("发送", f"成功发送 payload -> {raw_text}", color_success)
            return True
        except Exception as e:
            log_msg("错误", f"发送消息失败: {e}", color_error)
            return False

    async def _handle_received_message(self, raw_message: str):
        """解析并格式化展示服务端下发的消息"""
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            log_msg("接收", f"原始文本: {raw_message}", color_info)
            return

        if not isinstance(data, dict):
            log_msg("接收", f"数据: {data}", color_info)
            return

        msg_type = data.get("type")
        user = data.get("user")
        operate = data.get("operate")
        content = data.get("data")

        if msg_type == "memory":
            if operate == "sync":
                mem_list = content if isinstance(content, list) else []
                log_msg("同步", f"收到用户 [{user}] 的全量记忆 (共 {len(mem_list)} 条):", color_info)
                if mem_list:
                    for idx, item in enumerate(mem_list, 1):
                        print(f"     {color_dim(f'{idx:2d}.')} {item}")
                else:
                    print(f"     {color_dim('(记忆库为空)')}")
            elif operate == "add":
                log_msg("新增", f"用户 [{user}] 添加记忆: {color_bold(str(content))}", color_success)
            elif operate == "remove":
                log_msg("删除", f"用户 [{user}] 删除记忆: {color_warn(str(content))}", color_warn)
            else:
                log_msg("接收", f"记忆操作 [{operate}] 数据: {content}", color_info)
        else:
            log_msg("接收", f"JSON 消息: {json.dumps(data, ensure_ascii=False, indent=2)}", color_info)

    async def _receive_loop(self):
        """接收服务端消息的异步循环"""
        while self.running and self.ws and self.is_connected:
            try:
                message = await self.ws.recv()
                if isinstance(message, bytes):
                    message = message.decode("utf-8", errors="replace")
                await self._handle_received_message(message)
            except websockets.ConnectionClosed as e:
                log_msg("连接", f"WebSocket 连接关闭: code={e.code}, reason={e.reason or '(无原因)'}", color_warn)
                self.is_connected = False
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_msg("错误", f"接收消息异常: {e}", color_error)
                self.is_connected = False
                break

    def _parse_command(self, line: str):
        """
        解析用户输入的控制台命令
        返回 (cmd_type, kwargs)
        """
        line = line.strip()
        if not line:
            return "empty", {}

        # 检查是否为直接输入的 JSON
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                return "raw_obj", {"obj": obj}
            except json.JSONDecodeError as err:
                return "error", {"msg": f"无效的 JSON 格式: {err}"}

        parts = line.split(maxsplit=2)
        cmd = parts[0].lower()

        if cmd in ("help", "?"):
            return "help", {}

        if cmd in ("exit", "quit", "q"):
            return "exit", {}

        if cmd == "clear":
            return "clear", {}

        if cmd == "status":
            return "status", {}

        if cmd == "reconnect":
            return "reconnect", {}

        if cmd == "user":
            if len(parts) > 1:
                try:
                    uid = int(parts[1])
                    return "set_user", {"uid": uid}
                except ValueError:
                    return "error", {"msg": f"用户 ID 必须是整数: {parts[1]}"}
            return "get_user", {}

        if cmd in ("add", "del", "remove", "rm"):
            # 形式: add <内容> 或 add <uid> <内容>
            operate = "add" if cmd == "add" else "remove"
            if len(parts) < 2:
                return "error", {"msg": f"用法: {cmd} [uid] <记忆内容>"}

            # 判断第二项是否为数字 UID
            target_uid = self.default_user_id
            content = ""

            sub_parts = line.split(maxsplit=1)[1].strip()
            # 尝试用正则区分 "<uid> <content>" 和 "<content>"
            match = re.match(r"^(\d+)\s+(.+)$", sub_parts)
            if match:
                target_uid = int(match.group(1))
                content = match.group(2).strip()
            else:
                content = sub_parts

            return "memory", {"operate": operate, "uid": target_uid, "content": content}

        if cmd == "pull":
            # 形式: pull 或 pull <uid>
            target_uid = self.default_user_id
            if len(parts) > 1:
                try:
                    target_uid = int(parts[1])
                except ValueError:
                    return "error", {"msg": f"用户 ID 必须是整数: {parts[1]}"}
            return "pull", {"uid": target_uid}

        if cmd == "push":
            # 形式: push <m1, m2> 或 push <uid> <m1, m2>
            if len(parts) < 2:
                return "error", {"msg": "用法: push [uid] <记忆1, 记忆2, ...>"}

            sub_parts = line.split(maxsplit=1)[1].strip()
            target_uid = self.default_user_id
            raw_memories = sub_parts

            match = re.match(r"^(\d+)\s+(.+)$", sub_parts)
            if match:
                target_uid = int(match.group(1))
                raw_memories = match.group(2).strip()

            # 以逗号分割
            mem_list = [item.strip() for item in re.split(r"[,，]", raw_memories) if item.strip()]
            return "push", {"uid": target_uid, "memories": mem_list}

        if cmd == "raw":
            if len(parts) < 2:
                return "error", {"msg": "用法: raw <JSON 字符串>"}
            raw_str = line[3:].strip()
            try:
                obj = json.loads(raw_str)
                return "raw_obj", {"obj": obj}
            except json.JSONDecodeError as err:
                return "error", {"msg": f"JSON 解析失败: {err}"}

        return "unknown", {"cmd": cmd}

    async def _handle_command(self, line: str):
        """执行单个命令"""
        action, kwargs = self._parse_command(line)

        if action == "empty":
            return

        if action == "help":
            self.print_help()
            return

        if action == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            self.print_banner()
            return

        if action == "exit":
            log_msg("系统", "正在退出客户端...", color_warn)
            self.running = False
            if self.ws:
                await self.ws.close()
            return

        if action == "status":
            masked_key = self.auth_key[:2] + "****" + self.auth_key[-2:] if len(self.auth_key) >= 4 else "****"
            print(f"""
  连接状态:   {color_success("已连接") if self.is_connected else color_error("未连接")}
  服务地址:   {self.ws_url}
  鉴权密钥:   {masked_key}
  默认 UID:   {self.default_user_id}
""")
            return

        if action == "reconnect":
            log_msg("系统", "手动触发重新连接...", color_info)
            if self.ws:
                await self.ws.close()
            self.reconnect_requested.set()
            return

        if action == "get_user":
            log_msg("配置", f"当前默认用户 ID: {self.default_user_id}", color_info)
            return

        if action == "set_user":
            self.default_user_id = kwargs["uid"]
            log_msg("配置", f"已切换默认用户 ID 为: {self.default_user_id}", color_success)
            return

        if action == "memory":
            payload = {
                "user": kwargs["uid"],
                "type": "memory",
                "operate": kwargs["operate"],
                "data": kwargs["content"],
            }
            await self.send_json(payload)
            return

        if action == "pull":
            payload = {
                "user": kwargs["uid"],
                "type": "sync",
                "operate": "pull_all",
            }
            await self.send_json(payload)
            return

        if action == "push":
            payload = {
                "user": kwargs["uid"],
                "type": "sync",
                "operate": "push_all",
                "memory": kwargs["memories"],
            }
            await self.send_json(payload)
            return

        if action == "raw_obj":
            await self.send_json(kwargs["obj"]) # type:ignore
            return

        if action == "error":
            log_msg("错误", kwargs["msg"], color_error) # type:ignore
            return

        if action == "unknown":
            log_msg("提示", f"未知命令: '{kwargs['cmd']}'。输入 help 查看可用命令。", color_warn)
            return

    async def _input_worker(self, input_queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, stop_event: threading.Event):
        """后台线程读取标准输入并推送至队列"""
        def reader():
            while not stop_event.is_set():
                try:
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        loop.call_soon_threadsafe(input_queue.put_nowait, None)
                        break
                    loop.call_soon_threadsafe(input_queue.put_nowait, line.rstrip("\r\n"))
                except Exception:
                    break

        thread = threading.Thread(target=reader, daemon=True, name="StdinReaderThread")
        thread.start()

    async def run(self):
        """客户端主运行循环"""
        self.print_banner()

        if not self.auth_key:
            log_msg("警告", "未找到 auth_key，连接可能被拒绝。可使用 --key 参数或在 config.yaml 中配置。", color_warn)

        input_queue = asyncio.Queue()
        stop_event = threading.Event()
        loop = asyncio.get_running_loop()
        await self._input_worker(input_queue, loop, stop_event)

        connect_kwargs = get_ws_connect_kwargs(self.auth_key)

        while self.running:
            self.reconnect_requested.clear()
            log_msg("连接", f"正在连接 WebSocket -> {self.ws_url} ...", color_info)

            try:
                async with websockets.connect(self.ws_url, **connect_kwargs) as ws:
                    self.ws = ws
                    self.is_connected = True
                    log_msg("连接", color_success("WebSocket 连接已成功建立！"), color_success)
                    log_msg("提示", "可在此直接输入命令，输入 help 查看帮助。\n", color_dim)

                    receive_task = asyncio.create_task(self._receive_loop())

                    while self.running and self.is_connected and not self.reconnect_requested.is_set():
                        # 等待用户输入或接收中断
                        input_wait_task = asyncio.create_task(input_queue.get())
                        done, pending = await asyncio.wait(
                            [receive_task, input_wait_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        if input_wait_task in done:
                            line = input_wait_task.result()
                            if line is None:  # EOF 退出
                                log_msg("系统", "检测到输入流结束 (EOF)，准备退出...", color_warn)
                                self.running = False
                                break
                            await self._handle_command(line)
                        else:
                            input_wait_task.cancel()

                        if receive_task in done:
                            # 接收循环结束说明连接已断开
                            self.is_connected = False
                            break

                    if not receive_task.done():
                        receive_task.cancel()

            except getattr(websockets, "InvalidStatus", websockets.WebSocketException) as e:
                status_code = getattr(e, "status_code", None)
                if not status_code and hasattr(e, "response"):
                    status_code = getattr(e.response, "status_code", None) # type:ignore
                log_msg("失败", f"握手失败: HTTP 状态码 {status_code or '未知'}。请检查鉴权 key 是否正确！", color_error)
            except websockets.ConnectionClosed as e:
                if e.reason == "Invalid key":
                    log_msg("失败", "连接被拒绝: 鉴权失败 (Invalid key)，请检查 auth_key！", color_error)
                elif e.reason == "Only one connection allowed":
                    log_msg("失败", "连接被拒绝: 服务端只允许一个连接在线 (Only one connection allowed)！", color_error)
                else:
                    log_msg("断开", f"连接已断开: code={e.code}, reason={e.reason or '(无)'}", color_warn)
            except (ConnectionRefusedError, OSError) as e:
                log_msg("失败", f"无法连接到目标服务: {e}。请确认服务端已启动（如 python main.py）。", color_error)
            except Exception as e:
                log_msg("异常", f"连接异常: {type(e).__name__}: {e}", color_error)

            self.ws = None
            self.is_connected = False

            if not self.running:
                break

            # 如果不是手动重连，询问或等待
            if not self.reconnect_requested.is_set():
                if not sys.stdin.isatty():
                    # 管道模式下连接失败直接退出，避免死循环
                    break
                log_msg("提示", "将在 3 秒后尝试重连，或输入 exit 退出...", color_dim)
                try:
                    # 等待 3 秒重连，同时允许用户在此时输入命令（如 exit）
                    timeout = 3.0
                    start_time = asyncio.get_event_loop().time()
                    while (asyncio.get_event_loop().time() - start_time) < timeout:
                        if not input_queue.empty():
                            line = input_queue.get_nowait()
                            if line is None or line.strip() in ("exit", "quit", "q"):
                                self.running = False
                                break
                            await self._handle_command(line)
                        await asyncio.sleep(0.2)
                except asyncio.CancelledError:
                    break

        stop_event.set()
        log_msg("退出", "Mock WebSocket 客户端已关闭。", color_info)


# ============================== 命令行入口 ==============================

def main():
    parser = argparse.ArgumentParser(
        description="Web Search API - Link 端点 Mock WebSocket 客户端",
        usage="python mock_websocket_client.py [127.0.0.1:5212/link] [options]"
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="127.0.0.1:5212/link",
        help="目标 WebSocket 地址 (缺省使用默认值: 127.0.0.1:5212/link)"
    )
    parser.add_argument(
        "--key", "-k",
        dest="key",
        default=None,
        help="鉴权 Key (默认优先从 config.yaml 或环境变量 AUTH_KEY/LINK_KEY 获取)"
    )
    parser.add_argument(
        "--user", "-u",
        dest="default_user",
        type=int,
        default=1,
        help="默认操作的用户 ID (默认: 1)"
    )

    args = parser.parse_args()

    auth_key = find_auth_key(args.key)
    client = MockWebSocketClient(
        target_url=args.target,
        auth_key=auth_key,
        default_user_id=args.default_user
    )

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n" + color_warn("已收到中断信号 (Ctrl+C)，正在退出..."))


if __name__ == "__main__":
    main()
