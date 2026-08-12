# -*- coding: utf-8 -*-
"""QQ 空间好友动态自动点赞。"""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import requests
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ck import create_driver


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
LOGIN_SCRIPT = BASE_DIR / "ck.py"
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


def cookie_is_valid(qq, config):
    url = f"https://user.qzone.qq.com/{qq}/infocenter"
    try:
        response = requests.get(
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


def ensure_login(qq, config_path, manual):
    try:
        config = load_config(config_path)
        if config["qq"] == qq and cookie_is_valid(qq, config):
            return config
    except ValueError:
        pass

    logger.info("需要登录，正在打开 Chrome")
    if not open_login(qq, config_path, manual):
        raise LoginRequired("登录没有完成")
    return load_config(config_path)


def start_browser(config):
    driver = create_driver(None, headless=True)
    driver.set_page_load_timeout(30)
    driver.get("https://qzone.qq.com/")
    for part in config["cookie_str"].split(";"):
        name, separator, value = part.strip().partition("=")
        if not separator:
            continue
        try:
            driver.add_cookie({"name": name, "value": value, "domain": ".qq.com"})
        except WebDriverException:
            pass
    return driver


def get_nickname(button):
    try:
        item = button.find_element(
            By.XPATH, "./ancestor::li[contains(@class, 'f-single')][1]"
        )
        return item.find_element(By.CSS_SELECTOR, "a.nickname").text.strip() or "未知用户"
    except WebDriverException:
        return "未知用户"


def button_is_liked(button):
    try:
        return "item-on" in (button.get_attribute("class") or "").split()
    except StaleElementReferenceException:
        return True


def check_feed(driver, qq, attempted):
    url = f"https://user.qzone.qq.com/{qq}/infocenter?via=toolbar"
    logger.info("正在加载好友动态")
    driver.get(url)
    if "login" in driver.current_url.lower() or "ptlogin" in driver.current_url.lower():
        raise LoginRequired("登录状态已失效")

    try:
        WebDriverWait(driver, 15).until(
            lambda browser: browser.find_elements(By.CSS_SELECTOR, "li.f-single")
        )
    except TimeoutException:
        pass

    items = driver.find_elements(By.CSS_SELECTOR, "li.f-single")
    liked_count = 0
    while True:
        target = None
        for button in driver.find_elements(By.CSS_SELECTOR, "a.qz_like_btn_v3"):
            key = button.get_attribute("data-unikey")
            if key and key not in attempted and not button_is_liked(button):
                target = button
                attempted.add(key)
                break
        if target is None:
            break

        nickname = get_nickname(target)
        try:
            driver.execute_script("arguments[0].click()", target)
            WebDriverWait(driver, 5).until(lambda _browser: button_is_liked(target))
            liked_count += 1
            logger.info("点赞成功: %s", nickname)
        except (TimeoutException, WebDriverException):
            logger.warning("点赞失败: %s", nickname)
        time.sleep(1)

    return len(items), liked_count


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
    driver = None
    try:
        qq = resolve_qq(args.qq, config_path)
        config = ensure_login(qq, config_path, args.manual_login)
        driver = start_browser(config)
        attempted = set()

        while True:
            try:
                total, liked = check_feed(driver, qq, attempted)
                logger.info("本轮检查 %s 条动态，点赞 %s 条", total, liked)
            except LoginRequired:
                driver.quit()
                driver = None
                if not open_login(qq, config_path, args.manual_login):
                    raise LoginRequired("重新登录没有完成")
                config = load_config(config_path)
                driver = start_browser(config)
                continue
            except WebDriverException as exc:
                logger.warning("浏览器操作失败: %s", exc)

            if args.once:
                break
            time.sleep(args.interval)
    except (LoginRequired, ValueError, OSError, WebDriverException) as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("程序已停止")
    finally:
        if driver is not None:
            driver.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
