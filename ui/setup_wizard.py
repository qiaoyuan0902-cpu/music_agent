"""
首次启动配置向导
引导用户填写 API Key，保存到用户数据目录
"""
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QFrame, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor, QPalette


# ── 用户数据目录（打包后 .env 存这里）────────────────────────
def get_user_data_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "ClaudioFM"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "ClaudioFM"
    else:
        base = Path.home() / ".claudiofm"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_env_path() -> Path:
    return get_user_data_dir() / ".env"


def is_configured() -> bool:
    """检查是否已完成配置（.env 存在且含必要 key）"""
    env_path = get_env_path()
    if not env_path.exists():
        return False
    text = env_path.read_text(encoding="utf-8")
    has_anthropic = "ANTHROPIC_API_KEY=" in text or "ANTHROPIC_AUTH_TOKEN=" in text
    has_qweather  = "QWEATHER_API_KEY=" in text
    # 检查 key 不为空
    for line in text.splitlines():
        if line.startswith("ANTHROPIC_API_KEY=") or line.startswith("ANTHROPIC_AUTH_TOKEN="):
            if line.split("=", 1)[1].strip():
                has_anthropic = True
        if line.startswith("QWEATHER_API_KEY="):
            if line.split("=", 1)[1].strip():
                has_qweather = True
    return has_anthropic and has_qweather


def save_config(anthropic_key: str, qweather_key: str, base_url: str = ""):
    env_path = get_env_path()
    lines = [
        "# Claudio FM — 自动生成，可手动编辑",
        f"ANTHROPIC_API_KEY={anthropic_key.strip()}",
        f"QWEATHER_API_KEY={qweather_key.strip()}",
    ]
    if base_url.strip():
        lines.append(f"ANTHROPIC_BASE_URL={base_url.strip()}")
    lines += [
        "CLAUDE_MODEL=claude-sonnet-4-6",
        "MAX_HISTORY_TURNS=20",
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 颜色常量 ─────────────────────────────────────────────────
BG      = "#13111f"
CARD    = "#1c1a2e"
INPUT   = "#16142a"
ACCENT  = "#00ff88"
TEXT    = "#ffffff"
MUTED   = "#888899"
BORDER  = "#2a2840"


def _mono(size: int, bold: bool = False) -> QFont:
    for name in ("Menlo", "Monaco", "Courier New"):
        f = QFont(name, size)
        if f.exactMatch():
            f.setBold(bold)
            return f
    f = QFont("Courier New", size)
    f.setBold(bold)
    return f


class SetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Claudio FM — 初始配置")
        self.setFixedSize(480, 520)
        self.setModal(True)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 36, 40, 36)
        lay.setSpacing(0)

        # 标题
        title = QLabel("欢迎使用 Claudio FM")
        title.setFont(_mono(18, True))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{ACCENT}; letter-spacing:3px;")
        lay.addWidget(title)

        sub = QLabel("首次使用需要配置 API Key")
        sub.setFont(_mono(10))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{MUTED};")
        lay.addWidget(sub)
        lay.addSpacing(32)

        # Anthropic Key
        lay.addWidget(self._section_label("Anthropic API Key", "https://console.anthropic.com"))
        self.anthropic_input = self._make_input("sk-ant-...")
        lay.addWidget(self.anthropic_input)
        lay.addSpacing(6)

        hint1 = QLabel("用于驱动 AI 对话。前往 console.anthropic.com 免费注册获取。")
        hint1.setFont(_mono(9))
        hint1.setStyleSheet(f"color:{MUTED};")
        hint1.setWordWrap(True)
        lay.addWidget(hint1)
        lay.addSpacing(24)

        # QWeather Key
        lay.addWidget(self._section_label("QWeather API Key", "https://dev.qweather.com"))
        self.qweather_input = self._make_input("your_key_here")
        lay.addWidget(self.qweather_input)
        lay.addSpacing(6)

        hint2 = QLabel("用于显示实时天气。前往 dev.qweather.com 免费注册获取。")
        hint2.setFont(_mono(9))
        hint2.setStyleSheet(f"color:{MUTED};")
        hint2.setWordWrap(True)
        lay.addWidget(hint2)
        lay.addSpacing(24)

        # 可选：Base URL
        lay.addWidget(self._section_label("Anthropic Base URL（可选）", ""))
        self.baseurl_input = self._make_input("留空使用官方接口")
        lay.addWidget(self.baseurl_input)
        lay.addSpacing(32)

        # 错误提示
        self.error_lbl = QLabel("")
        self.error_lbl.setFont(_mono(9))
        self.error_lbl.setStyleSheet("color:#ff6666;")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.error_lbl)
        lay.addSpacing(8)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.confirm_btn = QPushButton("开始使用")
        self.confirm_btn.setFixedHeight(40)
        self.confirm_btn.setFont(_mono(11, True))
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.confirm_btn)
        lay.addLayout(btn_row)

    def _section_label(self, text: str, url: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(_mono(10, True))
        lbl.setStyleSheet(f"color:{TEXT}; letter-spacing:1px;")
        return lbl

    def _make_input(self, placeholder: str) -> QLineEdit:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedHeight(36)
        inp.setFont(_mono(10))
        inp.setStyleSheet(f"""
            QLineEdit {{
                background:{INPUT};
                color:{TEXT};
                border:1px solid {BORDER};
                border-radius:4px;
                padding:0 10px;
            }}
            QLineEdit:focus {{
                border:1px solid {ACCENT};
            }}
        """)
        return inp

    def _on_confirm(self):
        ak = self.anthropic_input.text().strip()
        qk = self.qweather_input.text().strip()
        bu = self.baseurl_input.text().strip()

        if not ak:
            self.error_lbl.setText("请填写 Anthropic API Key")
            return
        if not qk:
            self.error_lbl.setText("请填写 QWeather API Key")
            return

        save_config(ak, qk, bu)
        self.accept()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{ background:{BG}; }}
            QPushButton {{
                background:{ACCENT};
                color:#000000;
                border:none;
                border-radius:4px;
                font-weight:bold;
            }}
            QPushButton:hover {{ background:#00cc66; }}
            QPushButton:pressed {{ background:#009944; }}
        """)


# ── 独立运行预览 ──────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = SetupWizard()
    w.show()
    sys.exit(app.exec())
