# -*- coding: utf-8 -*-
"""QQ 空间好友动态自动点赞。"""

import argparse
import json
import logging
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
LOGIN_SCRIPT = BASE_DIR / "ck.py"
LIKE_URL = (
    "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/"
    "cgi-bin/likes/internal_dolike_app"
)
REQUEST_TIMEOUT = 15

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class LoginRequired(Exception):
    pass


def validate_qq(value):
    qq = str(value or "").strip()
    if not qq.isdigit() or not 5 <= len(qq) <= 12 or qq.startswith("0"):
        raise ValueError("QQ 号格式不正确")
    return qq


def load_config(path):
    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取配置: {exc}") from exc

    required = ("qq", "cookie_str", "user_agent", "g_tk")
    if not isinstance(config, dict) or any(
        config.get(key) in (None, "") for key in required
    ):
        raise ValueError("配置内容不完整")
    config["qq"] = validate_qq(config["qq"])
    return config


def resolve_qq(value, config_path):
    if value:
        return validate_qq(value)
    try:
        return load_config(config_path)["qq"]
    except ValueError:
        if sys.stdin.isatty():
            return validate_qq(input("请输入 QQ 号: "))
        raise ValueError("首次运行请使用 --qq 指定 QQ 号")


def request_headers(config):
    return {
        "User-Agent": config["user_agent"],
        "Cookie": config["cookie_str"],
    }


def cookie_is_valid(session, qq, config):
    url = f"https://user.qzone.qq.com/{qq}/infocenter"
    try:
        response = session.get(
            url,
            headers=request_headers(config),
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT,
        )
        return response.status_code == 200
    except requests.RequestException as exc:
        logger.warning("登录状态检查失败: %s", exc)
        return False


def open_login(qq, config_path, manual):
    command = [
        sys.executable,
        str(LOGIN_SCRIPT),
        "--qq",
        qq,
        "--config",
        str(config_path),
    ]
    if manual:
        command.append("--manual")
    return subprocess.run(command, check=False).returncode == 0


def ensure_login(session, qq, config_path, manual):
    try:
        config = load_config(config_path)
        if config["qq"] == qq and cookie_is_valid(session, qq, config):
            return config
    except ValueError:
        pass

    logger.info("需要登录，正在打开 Chrome")
    if not open_login(qq, config_path, manual):
        raise LoginRequired("登录没有完成")
    return load_config(config_path)


def like_post(session, qq, config, button):
    fields = {
        name: button.get(f"data-{name}")
        for name in ("unikey", "curkey", "appid", "typeid", "abstime")
    }
    if not all(fields.values()):
        return False

    feed_url = f"https://user.qzone.qq.com/{qq}/infocenter?via=toolbar"
    headers = {
        **request_headers(config),
        "Referer": feed_url,
        "Origin": "https://user.qzone.qq.com",
    }
    data = {
        "qzreferrer": feed_url,
        "opuin": qq,
        **fields,
        "from": "1",
        "fid": fields["unikey"].rsplit("/", 1)[-1],
        "active": "0",
        "fupdate": "1",
        "g_tk": str(config["g_tk"]),
    }

    try:
        response = session.post(
            LIKE_URL,
            params={"g_tk": config["g_tk"]},
            data=data,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("点赞请求失败: %s", exc)
        return False

    match = re.search(r'"?code"?\s*:\s*(-?\d+)', response.text)
    return bool(match and match.group(1) == "0")


def check_feed(session, qq, config, attempted):
    url = f"https://user.qzone.qq.com/{qq}/infocenter?via=toolbar"
    response = session.get(
        url,
        headers=request_headers(config),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    if "login" in response.url.lower() or "ptlogin" in response.url.lower():
        raise LoginRequired("登录状态已失效")

    items = BeautifulSoup(response.content, "html.parser").find_all(
        "li", class_="f-single"
    )
    success_count = 0
    for item in items:
        button = item.find("a", class_="qz_like_btn_v3")
        if not button or "item-on" in button.get("class", []):
            continue

        key = button.get("data-unikey")
        if not key or key in attempted:
            continue
        attempted.add(key)

        nickname = item.find("a", class_="nickname")
        nickname = nickname.get_text(strip=True) if nickname else "未知用户"
        if like_post(session, qq, config, button):
            success_count += 1
            logger.info("点赞成功: %s", nickname)
        else:
            logger.warning("点赞失败: %s", nickname)
        time.sleep(random.uniform(1, 2))

    return len(items), success_count


def interval_value(value):
    interval = float(value)
    if interval < 5:
        raise argparse.ArgumentTypeError("轮询间隔不能小于 5 秒")
    return interval


def parse_args():
    parser = argparse.ArgumentParser(description="QQ 空间好友动态自动点赞")
    parser.add_argument("--qq", help="QQ 号，首次运行时需要")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="配置文件路径"
    )
    parser.add_argument(
        "--interval", type=interval_value, default=30, help="轮询间隔，默认 30 秒"
    )
    parser.add_argument("--manual-login", action="store_true", help="登录时等待手动操作")
    parser.add_argument("--once", action="store_true", help="只检查一次")
    return parser.parse_args()


def main():
    args = parse_args()
    config_path = args.config.resolve()
    try:
        qq = resolve_qq(args.qq, config_path)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    session = requests.Session()
    attempted = set()
    try:
        config = ensure_login(session, qq, config_path, args.manual_login)
        while True:
            try:
                total, liked = check_feed(session, qq, config, attempted)
                logger.info("本轮检查 %s 条动态，点赞 %s 条", total, liked)
            except LoginRequired:
                config = ensure_login(session, qq, config_path, args.manual_login)
                continue
            except requests.RequestException as exc:
                logger.warning("读取动态失败: %s", exc)

            if args.once:
                break
            time.sleep(args.interval)
    except (LoginRequired, ValueError, OSError) as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("程序已停止")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
