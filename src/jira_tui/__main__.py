"""Jira Dashboard TUI 入口點

使用方式：
    uv run python -m jira_tui           # 啟動 TUI
    uv run python -m jira_tui auth login           # 新增/更新帳號
    uv run python -m jira_tui auth login --profile work
    uv run python -m jira_tui auth logout          # 刪除 active profile
    uv run python -m jira_tui auth logout --profile work
    uv run python -m jira_tui auth status          # 顯示所有帳號
    uv run python -m jira_tui auth switch work     # 切換 active profile
"""

from __future__ import annotations

import argparse
import sys


# ── CLI auth 子指令實作 ────────────────────────────────────────


def _cmd_auth_login(profile_name: str | None) -> None:
    """互動式填入帳號資訊，驗證成功後儲存"""
    import getpass
    import httpx
    from .auth import Profile, ProfileStore
    from .config import JiraClient

    print("=== Jira TUI 帳號設定 ===")

    # 決定 profile 名稱
    if not profile_name:
        existing = ProfileStore.get_active_name()
        default = existing or "default"
        profile_name = input(f"Profile 名稱 [{default}]: ").strip() or default

    host = input("Jira Host (例：https://xxx.atlassian.net): ").strip().rstrip("/")
    if not host:
        print("錯誤：Host 不能為空", file=sys.stderr)
        sys.exit(1)
    if not host.startswith("http"):
        print("錯誤：Host 格式錯誤，請以 https:// 開頭", file=sys.stderr)
        sys.exit(1)

    user = input("User (Email): ").strip()
    if not user:
        print("錯誤：Email 不能為空", file=sys.stderr)
        sys.exit(1)

    token = getpass.getpass("API Token (輸入時不顯示): ").strip()
    if not token:
        print("錯誤：Token 不能為空", file=sys.stderr)
        sys.exit(1)

    jql = input("預設 JQL（選填，直接 Enter 略過）: ").strip()

    print("\n驗證連線中...")
    try:
        client = JiraClient(host=host, user=user, token=token)
        myself = client.get_myself()
        display_name = myself.get("displayName", user)
        email = myself.get("emailAddress", "")
    except httpx.HTTPStatusError as e:
        print(
            f"驗證失敗：HTTP {e.response.status_code}，請確認 Token 是否正確",
            file=sys.stderr,
        )
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"連線錯誤：{e}，請確認 Host 是否正確", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"未預期錯誤：{e}", file=sys.stderr)
        sys.exit(1)

    profile = Profile(name=profile_name, host=host, user=user, token=token, jql=jql)
    ProfileStore.add_or_update(profile, set_active=True)

    print(f"\n✓ 驗證成功！歡迎，{display_name}（{email}）")
    print(f'✓ Profile "{profile_name}" 已儲存並設為 active')
    print(f"  儲存位置：{ProfileStore.CONFIG_FILE}")


def _cmd_auth_logout(profile_name: str | None) -> None:
    """刪除指定 profile（預設刪除 active）"""
    from .auth import ProfileStore

    if not profile_name:
        profile_name = ProfileStore.get_active_name()
        if not profile_name:
            print("目前沒有已儲存的 profile", file=sys.stderr)
            sys.exit(1)

    confirm = input(f'確定要刪除 profile "{profile_name}"？(y/N): ').strip().lower()
    if confirm != "y":
        print("已取消")
        return

    if ProfileStore.remove(profile_name):
        new_active = ProfileStore.get_active_name()
        if new_active:
            print(f'✓ Profile "{profile_name}" 已刪除，目前 active：{new_active}')
        else:
            print(f'✓ Profile "{profile_name}" 已刪除（無剩餘 profile）')
    else:
        print(f'錯誤：Profile "{profile_name}" 不存在', file=sys.stderr)
        sys.exit(1)


def _cmd_auth_status() -> None:
    """顯示所有 profile 與目前 active"""
    from .auth import ProfileStore

    profiles = ProfileStore.list_profiles()
    active = ProfileStore.get_active_name()

    if not profiles:
        print("目前沒有已儲存的 profile")
        print(f"\n執行 `jira_tui auth login` 來新增帳號")
        return

    print(f"儲存位置：{ProfileStore.CONFIG_FILE}")
    print(f"\n已儲存的 Profiles（共 {len(profiles)} 個）：\n")

    for name in profiles:
        p = ProfileStore.get(name)
        if p is None:
            continue
        marker = "* " if name == active else "  "
        active_label = " (active)" if name == active else ""
        print(f"{marker}{name}{active_label}")
        print(f"    Host:  {p.host}")
        print(f"    User:  {p.user}")
        token_preview = p.token[:4] + "****" if len(p.token) > 4 else "****"
        print(f"    Token: {token_preview}")
        if p.jql:
            print(f"    JQL:   {p.jql}")
        print()


def _cmd_auth_switch(profile_name: str) -> None:
    """切換 active profile"""
    from .auth import ProfileStore

    if ProfileStore.switch(profile_name):
        p = ProfileStore.get(profile_name)
        print(f'✓ 已切換到 profile "{profile_name}"')
        if p:
            print(f"  Host: {p.host}")
            print(f"  User: {p.user}")
    else:
        profiles = ProfileStore.list_profiles()
        print(f'錯誤：Profile "{profile_name}" 不存在', file=sys.stderr)
        if profiles:
            print(f"可用的 profiles：{', '.join(profiles)}", file=sys.stderr)
        sys.exit(1)


# ── argparse 主體 ──────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jira_tui",
        description="Jira Dashboard TUI",
    )
    subparsers = parser.add_subparsers(dest="command")

    # auth 指令
    auth_parser = subparsers.add_parser("auth", help="管理 Jira 帳號認證")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command")

    # auth login
    login_parser = auth_subparsers.add_parser("login", help="新增或更新帳號")
    login_parser.add_argument(
        "--profile",
        "-p",
        metavar="NAME",
        help="Profile 名稱（預設：互動式詢問）",
    )

    # auth logout
    logout_parser = auth_subparsers.add_parser("logout", help="刪除帳號")
    logout_parser.add_argument(
        "--profile",
        "-p",
        metavar="NAME",
        help="要刪除的 Profile 名稱（預設：active profile）",
    )

    # auth status
    auth_subparsers.add_parser("status", help="顯示所有帳號")

    # auth switch
    switch_parser = auth_subparsers.add_parser("switch", help="切換 active 帳號")
    switch_parser.add_argument("profile", metavar="NAME", help="要切換的 Profile 名稱")

    return parser


def main() -> None:
    """主程式入口"""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "auth":
        if args.auth_command == "login":
            _cmd_auth_login(getattr(args, "profile", None))
        elif args.auth_command == "logout":
            _cmd_auth_logout(getattr(args, "profile", None))
        elif args.auth_command == "status":
            _cmd_auth_status()
        elif args.auth_command == "switch":
            _cmd_auth_switch(args.profile)
        else:
            # `jira_tui auth` 不帶子指令 → 顯示 auth help
            parser.parse_args(["auth", "--help"])
    else:
        # 無參數 or 未知指令 → 啟動 TUI
        from .app import JiraDashboard

        app = JiraDashboard()
        app.run()


if __name__ == '__main__':
    main()
