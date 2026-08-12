"""Shared configuration and parsing helpers for the QZone scripts."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional


VERSION = "2.0.0"
QQ_PATTERN = re.compile(r"^[1-9]\d{4,11}$")
CALLBACK_CODE_PATTERN = re.compile(r"(?:[\"']?code[\"']?)\s*:\s*(-?\d+)")


class ConfigError(ValueError):
    """Raised when the local credential file is missing or malformed."""


def validate_qq(value: Any) -> str:
    qq = str(value or "").strip()
    if not QQ_PATTERN.fullmatch(qq):
        raise ConfigError("QQ 号应为 5 至 12 位数字，且不能以 0 开头")
    return qq


def cookie_value(cookie_header: str, name: str) -> Optional[str]:
    for item in cookie_header.split(";"):
        key, separator, value = item.strip().partition("=")
        if separator and key == name:
            return value
    return None


def calculate_g_tk(skey: str) -> int:
    """Calculate the QZone CSRF token (also known as bkn/g_tk)."""
    value = 5381
    for character in skey:
        value += (value << 5) + ord(character)
    return value & 0x7FFFFFFF


def extract_callback_code(response_text: str) -> Optional[int]:
    """Read a numeric code from QZone's JSON or JSONP response."""
    match = CALLBACK_CODE_PATTERN.search(response_text)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class Credentials:
    qq: str
    cookie_str: str
    user_agent: str
    g_tk: int
    updated_at: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Credentials":
        qq = validate_qq(data.get("qq"))
        cookie_str = str(data.get("cookie_str") or "").strip()
        user_agent = str(data.get("user_agent") or "").strip()
        if not cookie_str:
            raise ConfigError("配置中缺少 Cookie")
        if not user_agent:
            raise ConfigError("配置中缺少浏览器 User-Agent")

        raw_g_tk = data.get("g_tk")
        if raw_g_tk in (None, ""):
            skey = cookie_value(cookie_str, "p_skey") or cookie_value(cookie_str, "skey")
            if not skey:
                raise ConfigError("Cookie 中缺少 p_skey/skey，无法计算 g_tk")
            g_tk = calculate_g_tk(skey)
        else:
            try:
                g_tk = int(raw_g_tk)
            except (TypeError, ValueError) as exc:
                raise ConfigError("配置中的 g_tk 不是有效整数") from exc

        return cls(
            qq=qq,
            cookie_str=cookie_str,
            user_agent=user_agent,
            g_tk=g_tk,
            updated_at=str(data.get("updated_at") or ""),
        )


def load_credentials(path: Path) -> Credentials:
    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"无法读取配置文件: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("配置文件顶层必须是 JSON 对象")
    return Credentials.from_mapping(data)


def save_credentials(path: Path, credentials: Credentials) -> None:
    """Write credentials atomically so an interrupted login cannot corrupt them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    payload = asdict(credentials)
    if not payload["updated_at"]:
        payload["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as config_file:
            json.dump(payload, config_file, indent=2, ensure_ascii=False)
            config_file.write("\n")
        os.replace(temporary_path, path)
    except OSError:
        try:
            temporary_path.unlink(missing_ok=True)
        finally:
            raise


def read_qq_hint(path: Path) -> Optional[str]:
    """Read only the QQ number from a config, even if its Cookie has expired."""
    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
        if isinstance(data, dict):
            return validate_qq(data.get("qq"))
    except (OSError, json.JSONDecodeError, ConfigError):
        pass
    return None
