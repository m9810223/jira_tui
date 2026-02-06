"""Tree 佈局配置"""


class TreeLayout:
    """Tree 佈局配置 - 統一管理欄位寬度"""

    # 欄位寬度常數
    EXPAND_WIDTH = 2
    TYPE_WIDTH = 2
    KEY_WIDTH = 12
    STATUS_WIDTH = 16
    DATE_WIDTH = 5  # MM/DD 格式
    SP_WIDTH = 5    # Story Points 寬度 (例如 "8.000")
    EST_WIDTH = 7   # Aggregate Time Original Estimate 寬度 (例如 "1d2h30m")

    # Tree 結構常數
    MAX_DEPTH = 5
    GUIDE_DEPTH = 2

    def __init__(
        self,
        *,
        summary_width: int = 40,
        show_status: bool = True,
        show_dates: bool = True,
        show_sp: bool = True,
        show_est: bool = True,
    ):
        self._summary_width = summary_width
        self._show_status = show_status
        self._show_dates = show_dates
        self._show_sp = show_sp
        self._show_est = show_est

    @property
    def show_status(self) -> bool:
        return self._show_status

    @show_status.setter
    def show_status(self, value: bool) -> None:
        self._show_status = value

    @property
    def show_dates(self) -> bool:
        return self._show_dates

    @show_dates.setter
    def show_dates(self, value: bool) -> None:
        self._show_dates = value

    @property
    def show_sp(self) -> bool:
        return self._show_sp

    @show_sp.setter
    def show_sp(self, value: bool) -> None:
        self._show_sp = value

    @property
    def show_est(self) -> bool:
        return self._show_est

    @show_est.setter
    def show_est(self, value: bool) -> None:
        self._show_est = value

    @property
    def summary_width(self) -> int:
        return self._summary_width

    @summary_width.setter
    def summary_width(self, value: int) -> None:
        self._summary_width = max(20, value)

    @property
    def max_guide_width(self) -> int:
        """計算最大 guide 寬度（show_root=False 時）"""
        return (self.MAX_DEPTH - 1) * self.GUIDE_DEPTH

    def depth_padding(self, depth: int) -> int:
        """計算深度補齊空白寬度"""
        return (self.MAX_DEPTH - depth) * self.GUIDE_DEPTH

    @property
    def fields_width(self) -> int:
        """計算欄位區塊寬度"""
        width = 1  # space before timeline
        if self._show_sp:
            width += 1 + self.SP_WIDTH
        if self._show_est:
            width += 1 + self.EST_WIDTH
        if self._show_status:
            width += 1 + self.STATUS_WIDTH
        if self._show_dates:
            width += 1 + self.DATE_WIDTH + 1 + self.DATE_WIDTH  # start + due
        return width

    def width_before_timeline(self, depth: int) -> int:
        """計算 Timeline 之前的寬度（不含 guide）"""
        # expand + type + key + summary + depth_padding + fields
        return (
            self.EXPAND_WIDTH
            + self.TYPE_WIDTH
            + self.KEY_WIDTH
            + self._summary_width
            + self.depth_padding(depth)
            + self.fields_width
        )

    @property
    def total_fixed_width(self) -> int:
        """計算 Timeline 之前的固定寬度（含 guide，最深層 depth）"""
        return self.max_guide_width + self.width_before_timeline(self.MAX_DEPTH)
