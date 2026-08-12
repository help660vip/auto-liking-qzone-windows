# -*- coding: utf-8 -*-
"""Open Chrome, complete QZone login, and save the resulting credentials."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from qzone_utils import (
    ConfigError,
    Credentials,
    calculate_g_tk,
    cookie_value,
    read_qq_hint,
    save_credentials,
    validate_qq,
)


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = PROJECT_DIR / "config.json"
DEFAULT_DRIVER = PROJECT_DIR / "chromedriver.exe"


def resolve_qq(cli_value: Optional[str], config_path: Path) -> str:
    if cli_value:
        return validate_qq(cli_value)
    saved_qq = read_qq_hint(config_path)
    if saved_qq:
        return saved_qq
    if sys.stdin.isatty():
        return validate_qq(input("请输入要登录的 QQ 号: "))
    raise ConfigError("首次运行需要通过 --qq 指定 QQ 号")


def create_driver(driver_path: Optional[Path], proxy: Optional[str]):
    options = Options()
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    selected_driver = driver_path
    if selected_driver is None and DEFAULT_DRIVER.exists():
        selected_driver = DEFAULT_DRIVER
    if selected_driver is not None:
        selected_driver = selected_driver.expanduser().resolve()
        if not selected_driver.is_file():
            raise ConfigError(f"ChromeDriver 不存在: {selected_driver}")
        return webdriver.Chrome(
            service=Service(executable_path=str(selected_driver)), options=options
        )

    print("[登录] 未指定 ChromeDriver，将由 Selenium Manager 自动匹配")
    return webdriver.Chrome(options=options)


def try_automatic_login(driver, qq: str) -> None:
    print("[登录] 尝试点击浏览器中已保存的 QQ 账号")
    try:
        WebDriverWait(driver, 15).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "login_frame"))
        )
        try:
            avatar = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, f"img_out_{qq}"))
            )
        except TimeoutException:
            avatar = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#qlogin_list a"))
            )
        avatar.click()
    except (TimeoutException, WebDriverException) as exc:
        print(f"[登录] 自动点击未完成: {exc}")
        print("[登录] 请在浏览器中手动完成登录")
    finally:
        try:
            driver.switch_to.default_content()
        except WebDriverException:
            pass


def is_logged_in(driver) -> bool:
    current_url = driver.current_url.lower()
    return "user.qzone.qq.com" in current_url and "passport" not in current_url


def acquire_credentials(
    qq: str,
    config_path: Path,
    manual: bool,
    driver_path: Optional[Path],
    proxy: Optional[str],
    login_timeout: float,
) -> bool:
    driver = None
    try:
        print("[登录] 正在启动 Chrome")
        driver = create_driver(driver_path, proxy)
        driver.get("https://qzone.qq.com/")

        if manual:
            print("[登录] 请扫码或点击账号登录")
        else:
            try_automatic_login(driver, qq)

        print(f"[登录] 等待登录完成，最多 {int(login_timeout)} 秒")
        WebDriverWait(driver, login_timeout, poll_frequency=1).until(is_logged_in)

        target_url = f"https://user.qzone.qq.com/{qq}/infocenter?via=toolbar"
        driver.get(target_url)
        WebDriverWait(driver, 30).until(
            lambda browser: browser.execute_script("return document.readyState")
            == "complete"
        )

        cookies = driver.get_cookies()
        cookie_str = "; ".join(
            f"{item['name']}={item['value']}" for item in cookies
        )
        user_agent = driver.execute_script("return navigator.userAgent;")
        skey = cookie_value(cookie_str, "p_skey") or cookie_value(cookie_str, "skey")
        if not skey:
            raise ConfigError("登录 Cookie 中没有 p_skey/skey，请重新登录后再试")

        credentials = Credentials(
            qq=qq,
            cookie_str=cookie_str,
            user_agent=user_agent,
            g_tk=calculate_g_tk(skey),
        )
        save_credentials(config_path, credentials)
        print(f"[登录] 登录配置已保存到 {config_path}")
        return True
    except TimeoutException:
        print("[登录] 等待登录超时，未写入配置")
        return False
    except (ConfigError, OSError, WebDriverException) as exc:
        print(f"[登录] 失败: {exc}")
        if isinstance(exc, WebDriverException) and driver_path is None:
            print("[提示] 可手动下载匹配的 chromedriver.exe 并用 --driver 指定路径")
        return False
    finally:
        if driver is not None:
            driver.quit()


def positive_number(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="获取并保存 QQ 空间登录配置")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("hm",),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--qq", help="要登录的 QQ 号")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_FILE, help="配置保存路径"
    )
    parser.add_argument("--manual", action="store_true", help="不自动点击账号，等待手动登录")
    parser.add_argument("--driver", type=Path, help="本地 chromedriver.exe 路径")
    parser.add_argument("--proxy", help="Chrome 使用的代理，例如 http://127.0.0.1:7890")
    parser.add_argument(
        "--login-timeout",
        type=positive_number,
        default=180.0,
        help="等待登录的秒数（默认: 180）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = args.config.expanduser().resolve()
    try:
        qq = resolve_qq(args.qq, config_path)
    except ConfigError as exc:
        print(f"[登录] {exc}")
        return 2

    success = acquire_credentials(
        qq=qq,
        config_path=config_path,
        manual=args.manual or args.mode == "hm",
        driver_path=args.driver,
        proxy=args.proxy,
        login_timeout=args.login_timeout,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
