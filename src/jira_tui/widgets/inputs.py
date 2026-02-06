"""自訂輸入元件"""

from textual.widgets import Input
from textual.widgets import TextArea


class BlurInput(Input):
    """按 ESC 可取消焦點的 Input"""

    BINDINGS = [
        ('escape', 'blur', '取消焦點'),
    ]

    def action_blur(self) -> None:
        self.app.set_focus(None)


class BlurTextArea(TextArea):
    """按 ESC 可取消焦點的 TextArea"""

    BINDINGS = [
        ('escape', 'blur', '取消焦點'),
    ]

    def action_blur(self) -> None:
        self.app.set_focus(None)
