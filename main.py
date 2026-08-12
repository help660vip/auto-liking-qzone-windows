# -*- coding: utf-8 -*-
"""Poll QZone feeds and like posts that have not been liked yet."""

from __future__ import annotations

import argparse
import logging
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from qzone_utils import (
    VERSION,
    ConfigError,
    Credentials,
    extract_callback_code,
    load_credentials,
    read_qq_hint,
    validate_qq,
)


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = PROJECT_DIR / "config.json"
DEFAULT_LOG_FILE = PROJECT_DIR / "app.log"
CK_SCRIPT = PROJECT_DIR / "ck.py"
REQUEST_TIMEOUT = (5, 20)

LOGGER = logging.getLogger("qzone-auto-liker")


class AuthenticationExpired(RuntimeError):
    """Raised when QZone redirects a request to its login page."""


@dataclass(frozen=True)
class LikeTarget:
    unikey: str
    curkey: str
    appid: str
    typeid: str
    abstime: str
    nickname: str


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def configure_logging(log_file: Optional[Path], verbose: bool) -> None:
    handlers = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )


def positive_number(value: str) -> float:
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return number


def non_negative_number(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("不能小于 0")
    return number


def resolve_qq(cli_value: Optional[str], config_path: Path) -> str:
    if cli_value:
        return validate_qq(cli_value)
    saved_qq = read_qq_hint(config_path)
    if saved_qq:
        return saved_qq
    if sys.stdin.isatty():
        return validate_qq(input("请输入要登录的 QQ 号: "))
    raise ConfigError("首次运行需要通过 --qq 指定 QQ 号")


class QZoneAutoLiker:
    def __init__(
        self,
        qq: str,
        config_path: Path,
        manual_login: bool,
        retry_delay: float,
    ) -> None:
        self.qq = qq
        self.config_path = config_path
        self.manual_login = manual_login
        self.retry_delay = retry_delay
        self.session = build_session()
        self.credentials: Optional[Credentials] = None
        self.last_attempts: Dict[str, float] = {}

    def _headers(self) -> Dict[str, str]:
        if self.credentials is None:
            raise ConfigError("尚未加载登录配置")
        return {
            "User-Agent": self.credentials.user_agent,
            "Cookie": self.credentials.cookie_str,
        }

    def load_config(self) -> bool:
        try:
            credentials = load_credentials(self.config_path)
        except ConfigError as exc:
            LOGGER.info("登录配置不可用: %s", exc)
            self.credentials = None
            return False
        if credentials.qq != self.qq:
            LOGGER.warning(
                "配置中的 QQ (%s) 与当前 QQ (%s) 不一致", credentials.qq, self.qq
            )
            self.credentials = None
            return False
        self.credentials = credentials
        return True

    def check_cookie_valid(self) -> bool:
        if self.credentials is None:
            return False
        url = f"https://user.qzone.qq.com/{self.qq}/infocenter"
        try:
            response = self.session.get(
                url,
                headers=self._headers(),
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            LOGGER.warning("Cookie 校验请求失败: %s", exc)
            return False

        if response.status_code == 200:
            return True
        LOGGER.warning("Cookie 校验未通过，HTTP %s", response.status_code)
        return False

    def call_login(self) -> bool:
        if not CK_SCRIPT.exists():
            LOGGER.error("找不到登录脚本: %s", CK_SCRIPT)
            return False

        command = [
            sys.executable,
            str(CK_SCRIPT),
            "--qq",
            self.qq,
            "--config",
            str(self.config_path),
        ]
        if self.manual_login:
            command.append("--manual")

        LOGGER.info("正在打开浏览器刷新登录状态")
        try:
            completed = subprocess.run(command, check=False)
        except OSError as exc:
            LOGGER.error("无法启动登录脚本: %s", exc)
            return False
        if completed.returncode != 0:
            LOGGER.error("登录脚本退出，代码 %s", completed.returncode)
            return False
        return True

    def ensure_authenticated(self) -> bool:
        if self.load_config() and self.check_cookie_valid():
            return True
        if not self.call_login():
            return False
        if not self.load_config():
            LOGGER.error("登录完成后仍无法读取配置")
            return False
        if not self.check_cookie_valid():
            LOGGER.error("新获取的 Cookie 未通过校验")
            return False
        return True

    def _feed_url(self) -> str:
        return f"https://user.qzone.qq.com/{self.qq}/infocenter?via=toolbar"

    def _extract_target(self, item) -> Optional[LikeTarget]:
        like_button = item.find("a", class_="qz_like_btn_v3")
        if not like_button or "item-on" in like_button.get("class", []):
            return None

        fields = {
            name: like_button.get(f"data-{name}")
            for name in ("unikey", "curkey", "appid", "typeid", "abstime")
        }
        if any(value is None or value == "" for value in fields.values()):
            LOGGER.debug("跳过缺少点赞参数的动态")
            return None

        nickname_element = item.find("a", class_="nickname")
        nickname = (
            nickname_element.get_text(strip=True) if nickname_element else "未知用户"
        )
        return LikeTarget(nickname=nickname, **fields)

    def _can_attempt(self, key: str, now: float) -> bool:
        previous = self.last_attempts.get(key)
        if previous is not None and now - previous < self.retry_delay:
            return False
        self.last_attempts[key] = now
        expiry = now - (self.retry_delay * 2)
        self.last_attempts = {
            item_key: attempted_at
            for item_key, attempted_at in self.last_attempts.items()
            if attempted_at >= expiry
        }
        return True

    def do_like(self, target: LikeTarget) -> Tuple[bool, str]:
        if self.credentials is None:
            return False, "尚未加载登录配置"

        endpoint = (
            "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/"
            "cgi-bin/likes/internal_dolike_app"
        )
        referer = self._feed_url()
        headers = {
            **self._headers(),
            "Referer": referer,
            "Origin": "https://user.qzone.qq.com",
        }
        payload = {
            "qzreferrer": referer,
            "opuin": self.qq,
            "unikey": target.unikey,
            "curkey": target.curkey,
            "from": "1",
            "appid": target.appid,
            "typeid": target.typeid,
            "abstime": target.abstime,
            "fid": target.unikey.rsplit("/", 1)[-1],
            "active": "0",
            "fupdate": "1",
            "g_tk": str(self.credentials.g_tk),
        }

        try:
            response = self.session.post(
                endpoint,
                params={"g_tk": self.credentials.g_tk},
                data=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return False, f"请求失败: {exc}"

        code = extract_callback_code(response.text)
        if code == 0:
            return True, "成功"
        if code is None:
            return False, "服务端响应中没有可识别的结果码"
        return False, f"服务端结果码 {code}"

    def poll_once(self) -> Tuple[int, int]:
        try:
            response = self.session.get(
                self._feed_url(),
                headers=self._headers(),
                allow_redirects=True,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException:
            raise

        final_url = response.url.lower()
        if "login" in final_url or "ptlogin" in final_url:
            raise AuthenticationExpired("动态页已跳转到登录页面")

        soup = BeautifulSoup(response.content, "html.parser")
        items = soup.find_all("li", class_="f-single")
        attempted = 0
        succeeded = 0
        now = time.monotonic()

        for item in items:
            target = self._extract_target(item)
            if target is None or not self._can_attempt(target.unikey, now):
                continue
            attempted += 1
            LOGGER.info("发现未点赞动态: %s", target.nickname)
            success, message = self.do_like(target)
            if success:
                succeeded += 1
                LOGGER.info("点赞成功: %s", target.nickname)
            else:
                LOGGER.warning("点赞失败: %s（%s）", target.nickname, message)
            time.sleep(random.uniform(1.0, 2.5))

        LOGGER.debug("本轮读取 %s 条动态，尝试 %s 次", len(items), attempted)
        return attempted, succeeded

    def run(
        self,
        interval: float,
        jitter: float,
        auth_check_interval: float,
        run_once: bool,
    ) -> int:
        LOGGER.info("QZone Auto Liker v%s 启动，账号 %s", VERSION, self.qq)
        if not self.ensure_authenticated():
            return 1
        LOGGER.info("登录状态有效，开始检查动态")
        next_auth_check = time.monotonic() + auth_check_interval

        while True:
            try:
                if time.monotonic() >= next_auth_check:
                    if not self.check_cookie_valid():
                        LOGGER.warning("登录状态已失效，尝试重新登录")
                        if not self.ensure_authenticated():
                            return 1
                    next_auth_check = time.monotonic() + auth_check_interval

                attempted, succeeded = self.poll_once()
                if run_once:
                    LOGGER.info("单次检查结束：尝试 %s，成功 %s", attempted, succeeded)
                    return 0
            except AuthenticationExpired as exc:
                LOGGER.warning("%s，尝试重新登录", exc)
                if not self.ensure_authenticated():
                    return 1
            except requests.RequestException as exc:
                LOGGER.warning("动态请求暂时失败: %s", exc)
                if run_once:
                    return 1
            except KeyboardInterrupt:
                LOGGER.info("收到退出信号，程序已停止")
                return 0
            except Exception:
                LOGGER.exception("检查动态时发生未预期错误")
                if run_once:
                    return 1

            time.sleep(interval + random.uniform(0, jitter))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QQ 空间好友动态自动点赞工具")
    parser.add_argument("--qq", help="QQ 号；首次运行必填，之后会从配置读取")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help=f"凭据文件路径（默认: {DEFAULT_CONFIG_FILE.name}）",
    )
    parser.add_argument(
        "--interval",
        type=positive_number,
        default=30.0,
        help="动态轮询基础间隔，单位秒（默认: 30）",
    )
    parser.add_argument(
        "--jitter",
        type=non_negative_number,
        default=5.0,
        help="每轮附加的随机等待上限，单位秒（默认: 5）",
    )
    parser.add_argument(
        "--retry-delay",
        type=positive_number,
        default=300.0,
        help="同一动态再次尝试前的等待时间，单位秒（默认: 300）",
    )
    parser.add_argument(
        "--auth-check-interval",
        type=positive_number,
        default=300.0,
        help="主动校验登录状态的间隔，单位秒（默认: 300）",
    )
    parser.add_argument("--manual-login", action="store_true", help="登录时等待手动扫码或点击")
    parser.add_argument("--once", action="store_true", help="只检查一轮后退出")
    parser.add_argument("--no-log-file", action="store_true", help="不写入 app.log")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(None if args.no_log_file else DEFAULT_LOG_FILE, args.verbose)
    try:
        qq = resolve_qq(args.qq, args.config.resolve())
    except ConfigError as exc:
        LOGGER.error("%s", exc)
        return 2

    application = QZoneAutoLiker(
        qq=qq,
        config_path=args.config.resolve(),
        manual_login=args.manual_login,
        retry_delay=args.retry_delay,
    )
    return application.run(
        interval=args.interval,
        jitter=args.jitter,
        auth_check_interval=args.auth_check_interval,
        run_once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
