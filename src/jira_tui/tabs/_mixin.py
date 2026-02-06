"""Tab 共用 Mixin"""

from ..config import Config
from ..config import JiraClient


class JiraClientMixin:
    """提供 JiraClient 存取的 Mixin

    使用此 Mixin 的 Widget 必須掛載於具有 config 和 _get_jira_client 屬性的 App 下。
    """

    @property
    def config(self) -> Config:
        return self.app.config  # pyright: ignore[reportAttributeAccessIssue]

    def _get_jira_client(self, *, silent: bool = False) -> JiraClient | None:
        """建立 JiraClient

        Args:
            silent: 若為 True，設定不完整時不顯示通知

        Returns:
            JiraClient 實例，若設定不完整則回傳 None
        """
        if not all([self.config.host, self.config.user, self.config.token]):
            if not silent:
                self.app.notify('請先設定 API 連線', severity='error')  # pyright: ignore[reportAttributeAccessIssue]
            return None
        return self.app._get_jira_client()  # pyright: ignore[reportAttributeAccessIssue]
