"""自訂 DataTable"""

from textual.widgets import DataTable


class JqlDataTable(DataTable):
    """Page Up/Down 會跳到第一列/最後一列的 DataTable"""

    def action_page_up(self) -> None:
        """Page Up 移動游標到第一列"""
        if self.row_count > 0:
            self.move_cursor(row=0)

    def action_page_down(self) -> None:
        """Page Down 移動游標到最後一列"""
        if self.row_count > 0:
            self.move_cursor(row=self.row_count - 1)
