"""Profile 管理模組

儲存格式：~/.config/jira_tui/profiles.json
{
  "active": "default",
  "profiles": {
    "default": {
      "host": "https://xxx.atlassian.net",
      "user": "user@example.com",
      "token": "ATATT3x...",
      "jql": ""
    }
  }
}
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path


@dataclass
class Profile:
    """單一 Jira 帳號設定"""

    name: str
    host: str
    user: str
    token: str
    jql: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("name")  # name 是 key，不存在 value 裡
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "Profile":
        return cls(
            name=name,
            host=data.get("host", ""),
            user=data.get("user", ""),
            token=data.get("token", ""),
            jql=data.get("jql", ""),
        )


class ProfileStore:
    """管理 ~/.config/jira_tui/profiles.json"""

    CONFIG_DIR: Path = Path.home() / ".config" / "jira_tui"
    CONFIG_FILE: Path = CONFIG_DIR / "profiles.json"

    _EMPTY: dict = {"active": None, "profiles": {}}

    # ── 基礎 I/O ──────────────────────────────────────────────

    @classmethod
    def _load_raw(cls) -> dict:
        """讀取原始 JSON，不存在時回傳空結構"""
        if not cls.CONFIG_FILE.exists():
            return {"active": None, "profiles": {}}
        try:
            with cls.CONFIG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"active": None, "profiles": {}}
            data.setdefault("active", None)
            data.setdefault("profiles", {})
            return data
        except (json.JSONDecodeError, OSError):
            return {"active": None, "profiles": {}}

    @classmethod
    def _save_raw(cls, data: dict) -> None:
        """寫入 JSON，自動建立目錄，設定 0o600 權限"""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = cls.CONFIG_FILE.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(cls.CONFIG_FILE)
        # 設定只有擁有者可讀寫
        os.chmod(cls.CONFIG_FILE, 0o600)

    # ── 公開 API ──────────────────────────────────────────────

    @classmethod
    def list_profiles(cls) -> list[str]:
        """回傳所有 profile 名稱列表"""
        data = cls._load_raw()
        return list(data["profiles"].keys())

    @classmethod
    def get_active_name(cls) -> str | None:
        """回傳目前 active profile 的名稱"""
        data = cls._load_raw()
        active = data.get("active")
        profiles = data.get("profiles", {})
        if active and active in profiles:
            return active
        # active 失效時取第一個可用的
        if profiles:
            return next(iter(profiles))
        return None

    @classmethod
    def get_active(cls) -> Profile | None:
        """回傳目前 active Profile 物件，無設定時回傳 None"""
        data = cls._load_raw()
        active = data.get("active")
        profiles = data.get("profiles", {})

        if active and active in profiles:
            return Profile.from_dict(active, profiles[active])
        if profiles:
            name = next(iter(profiles))
            return Profile.from_dict(name, profiles[name])
        return None

    @classmethod
    def get(cls, name: str) -> Profile | None:
        """依名稱取得 Profile，不存在回傳 None"""
        data = cls._load_raw()
        profiles = data.get("profiles", {})
        if name in profiles:
            return Profile.from_dict(name, profiles[name])
        return None

    @classmethod
    def add_or_update(cls, profile: Profile, *, set_active: bool = True) -> None:
        """新增或更新 profile，預設同時設為 active"""
        data = cls._load_raw()
        data["profiles"][profile.name] = profile.to_dict()
        if set_active or data.get("active") is None:
            data["active"] = profile.name
        cls._save_raw(data)

    @classmethod
    def remove(cls, name: str) -> bool:
        """刪除指定 profile。若刪除的是 active，自動改為第一個剩餘的。
        回傳 True 表示成功刪除，False 表示 profile 不存在。"""
        data = cls._load_raw()
        profiles = data.get("profiles", {})
        if name not in profiles:
            return False
        del profiles[name]
        data["profiles"] = profiles
        if data.get("active") == name:
            data["active"] = next(iter(profiles)) if profiles else None
        cls._save_raw(data)
        return True

    @classmethod
    def switch(cls, name: str) -> bool:
        """切換 active profile。回傳 True 表示成功，False 表示 profile 不存在。"""
        data = cls._load_raw()
        if name not in data.get("profiles", {}):
            return False
        data["active"] = name
        cls._save_raw(data)
        return True
