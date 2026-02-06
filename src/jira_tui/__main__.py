"""Jira Dashboard TUI 入口點

使用方式：
    uv run python -m jira2
    或
    uv run jira2
"""

from .app import JiraDashboard


def main() -> None:
    """主程式入口"""
    app = JiraDashboard()
    app.run()


if __name__ == '__main__':
    main()
