# -*- coding: utf-8 -*-
"""通过 Chrome 登录 QQ 空间并保存 Cookie。"""

import argparse
import json
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
DEFAULT_DRIVER = BASE_DIR / "chromedriver.exe"


def validate_qq(value):
    qq = str(value or "").strip()
    if not qq.isdigit() or not 5 <= len(qq) <= 12 or qq.startswith("0"):
        raise ValueError("QQ 号格式不正确")
    return qq


def resolve_qq(value, config_path):
    if value:
        return validate_qq(value)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            return validate_qq(json.load(file).get("qq"))
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        if sys.stdin.isatty():
            return validate_qq(input("请输入 QQ 号: "))
        raise ValueError("首次运行请使用 --qq 指定 QQ 号")


def calculate_g_tk(skey):
    value = 5381
    for character in skey:
        value += (value << 5) + ord(character)
    return value & 0x7FFFFFFF


def create_driver(driver_path):
    options = Options()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    selected = driver_path
    if selected is None and DEFAULT_DRIVER.exists():
        selected = DEFAULT_DRIVER
    if selected is not None:
        selected = selected.expanduser().resolve()
        if not selected.is_file():
            raise ValueError(f"找不到 ChromeDriver: {selected}")
        return webdriver.Chrome(
            service=Service(executable_path=str(selected)), options=options
        )
    return webdriver.Chrome(options=options)


def click_saved_account(driver, qq):
    try:
        time.sleep(2)
        driver.switch_to.frame("login_frame")
        try:
            driver.find_element(By.ID, f"img_out_{qq}").click()
        except WebDriverException:
            driver.find_element(By.CSS_SELECTOR, "#qlogin_list a").click()
    except WebDriverException:
        print("[登录] 未找到已保存账号，请手动登录")
    finally:
        try:
            driver.switch_to.default_content()
        except WebDriverException:
            pass


def wait_for_login(driver, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        url = driver.current_url.lower()
        if "user.qzone.qq.com" in url and "passport" not in url:
            return True
        time.sleep(1)
    return False


def save_config(driver, qq, config_path):
    cookies = driver.get_cookies()
    cookie_str = "; ".join(
        f"{cookie['name']}={cookie['value']}" for cookie in cookies
    )
    cookie_map = {cookie["name"]: cookie["value"] for cookie in cookies}
    skey = cookie_map.get("p_skey") or cookie_map.get("skey")
    if not skey:
        raise ValueError("登录 Cookie 中缺少 p_skey/skey")

    data = {
        "qq": qq,
        "cookie_str": cookie_str,
        "user_agent": driver.execute_script("return navigator.userAgent;"),
        "g_tk": calculate_g_tk(skey),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_name(f"{config_path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    temporary.replace(config_path)


def login(qq, config_path, manual, driver_path):
    driver = None
    try:
        print("[登录] 正在启动 Chrome")
        driver = create_driver(driver_path)
        driver.get("https://qzone.qq.com/")
        if manual:
            print("[登录] 请在浏览器中完成登录")
        else:
            click_saved_account(driver, qq)

        if not wait_for_login(driver):
            print("[登录] 等待登录超时")
            return False

        driver.get(f"https://user.qzone.qq.com/{qq}/infocenter?via=toolbar")
        time.sleep(3)
        save_config(driver, qq, config_path)
        print(f"[登录] 配置已保存到 {config_path}")
        return True
    except (ValueError, OSError, WebDriverException) as exc:
        print(f"[登录] 失败: {exc}")
        return False
    finally:
        if driver is not None:
            driver.quit()


def parse_args():
    parser = argparse.ArgumentParser(description="登录 QQ 空间并保存 Cookie")
    parser.add_argument("mode", nargs="?", choices=("hm",), help=argparse.SUPPRESS)
    parser.add_argument("--qq", help="QQ 号")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="配置文件路径"
    )
    parser.add_argument("--manual", action="store_true", help="等待手动登录")
    parser.add_argument("--driver", type=Path, help="本地 chromedriver.exe 路径")
    return parser.parse_args()


def main():
    args = parse_args()
    config_path = args.config.resolve()
    try:
        qq = resolve_qq(args.qq, config_path)
    except ValueError as exc:
        print(f"[登录] {exc}")
        return 2
    manual = args.manual or args.mode == "hm"
    return 0 if login(qq, config_path, manual, args.driver) else 1


if __name__ == "__main__":
    raise SystemExit(main())
