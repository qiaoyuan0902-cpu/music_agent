"""
首次启动配置向导 — 支持 Claude / OpenAI / 通义千问
"""
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QApplication, QButtonGroup, QRadioButton,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


# ── 用户数据目录 ──────────────────────────────────────────────
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
    env_path = get_env_path()
    if not env_path.exists():
        return False
    text = env_path.read_text(encoding="utf-8")
    provider = ""
    has_key = False
    for line in text.splitlines():
        if line.startswith("LLM_PROVIDER="):
            provider = line.split("=", 1)[1].strip()
        if line.startswith("ANTHROPIC_AUTH_TOKEN=") and line.split("=", 1)[1].strip():
            has_key = True
        if line.startswith("OPENAI_API_KEY=") and line.split("=", 1)[1].strip():
            has_key = True
        if line.startswith("ANTHROPIC_API_KEY=") and line.split("=", 1)[1].strip():
            has_key = True
    return provider != "" and has_key


def save_config(provider: str, api_key: str, base_url: str = "", model: str = ""):
    env_path = get_env_path()
    lines = ["# Claudio FM — 自动生成，可手动编辑", f"LLM_PROVIDER={provider}"]
    if provider == "claude":
        lines.append(f"ANTHROPIC_AUTH_TOKEN={api_key.strip()}")
        if base_url.strip():
            lines.append(f"ANTHROPIC_BASE_URL={base_url.strip()}")
        lines.append(f"CLAUDE_MODEL={model.strip() or 'claude-sonnet-4-6'}")
    else:
        lines.append(f"OPENAI_API_KEY={api_key.strip()}")
        if provider == "qwen":
            lines.append(f"OPENAI_BASE_URL={base_url.strip() or 'https://dashscope.aliyuncs.com/compatible-mode/v1'}")
            lines.append(f"OPENAI_MODEL={model.strip() or 'qwen-max'}")
        else:
            if base_url.strip():
                lines.append(f"OPENAI_BASE_URL={base_url.strip()}")
            lines.append(f"OPENAI_MODEL={model.strip() or 'gpt-4o'}")
    lines.append("MAX_HISTORY_TURNS=20")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 颜色常量 ─────────────────────────────────────────────────
BG     = "#13111f"
INPUT  = "#16142a"
ACCENT = "#00ff88"
TEXT   = "#ffffff"
MUTED  = "#888899"
BORDER = "#2a2840"


def _mono(size: int, bold: bool = False) -> QFont:
    for name in ("Menlo", "Monaco", "Courier New"):
        f = QFont(name, size)
        if f.exactMatch():
            f.setBold(bold)
            return f
    f = QFont("Courier New", size)
    f.setBold(bold)
    return f


# ── Provider 配置表（必须在 SetupWizard 之前定义）────────────
_PROVIDER_DEFAULTS = {
    "claude": {
        "label":       "Claude (Anthropic)",
        "key_hint":    "sk-ant-... 或代理 token",
        "url_hint":    "留空使用官方接口",
        "url_prefill": "",
        "model_hint":  "claude-sonnet-4-6",
        "key_doc":     "前往 console.anthropic.com 获取",
    },
    "openai": {
        "label":       "OpenAI (GPT / Codex)",
        "key_hint":    "sk-...",
        "url_hint":    "留空使用官方接口，或填 Azure/代理地址",
        "url_prefill": "",
        "model_hint":  "gpt-4o",
        "key_doc":     "前往 platform.openai.com 获取",
    },
    "qwen": {
        "label":       "通义千问 (阿里云)",
        "key_hint":    "sk-...",
        "url_hint":    "DashScope 兼容接口（已预填）",
        "url_prefill": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_hint":  "qwen-max",
        "key_doc":     "前往 dashscope.aliyuncs.com 获取",
    },
}


class SetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Claudio FM — 初始配置")
        self.setFixedSize(500, 540)
        self.setModal(True)
        self._provider = "claude"
        self._build_ui()
        self._apply_style()
        self._on_provider_changed("claude")

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(0)

        title = QLabel("欢迎使用 Claudio FM")
        title.setFont(_mono(18, True))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color:{ACCENT}; letter-spacing:3px;")
        lay.addWidget(title)

        sub = QLabel("选择 AI 服务并填写 API Key")
        sub.setFont(_mono(10))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{MUTED};")
        lay.addWidget(sub)
        lay.addSpacing(24)

        # Provider 选择
        prov_row = QHBoxLayout()
        prov_row.setSpacing(8)
        self._btn_group = QButtonGroup(self)
        for pid, cfg in _PROVIDER_DEFAULTS.items():
            btn = QRadioButton(cfg["label"])
            btn.setFont(_mono(10))
            btn.setChecked(pid == "claude")
            btn.toggled.connect(
                lambda checked, p=pid: self._on_provider_changed(p) if checked else None
            )
            self._btn_group.addButton(btn)
            prov_row.addWidget(btn)
        lay.addLayout(prov_row)
        lay.addSpacing(24)

        # API Key
        self._key_label = QLabel("API Key")
        self._key_label.setFont(_mono(10, True))
        self._key_label.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(self._key_label)
        self.key_input = self._make_input("")
        lay.addWidget(self.key_input)
        lay.addSpacing(4)
        self._key_doc = QLabel("")
        self._key_doc.setFont(_mono(9))
        self._key_doc.setStyleSheet(f"color:{MUTED};")
        lay.addWidget(self._key_doc)
        lay.addSpacing(16)

        # Base URL
        url_lbl = QLabel("Base URL（可选）")
        url_lbl.setFont(_mono(10, True))
        url_lbl.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(url_lbl)
        self.url_input = self._make_input("")
        lay.addWidget(self.url_input)
        lay.addSpacing(16)

        # Model
        model_lbl = QLabel("模型（可选）")
        model_lbl.setFont(_mono(10, True))
        model_lbl.setStyleSheet(f"color:{TEXT};")
        lay.addWidget(model_lbl)
        self.model_input = self._make_input("")
        lay.addWidget(self.model_input)
        lay.addSpacing(24)

        self.error_lbl = QLabel("")
        self.error_lbl.setFont(_mono(9))
        self.error_lbl.setStyleSheet("color:#ff6666;")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.error_lbl)
        lay.addSpacing(8)

        btn = QPushButton("开始使用")
        btn.setFixedHeight(40)
        btn.setFont(_mono(11, True))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._on_confirm)
        lay.addWidget(btn)

    def _make_input(self, placeholder: str) -> QLineEdit:
        inp = QLineEdit()
        inp.setPlaceholderText(placeholder)
        inp.setFixedHeight(36)
        inp.setFont(_mono(10))
        inp.setStyleSheet(f"""
            QLineEdit {{
                background:{INPUT}; color:{TEXT};
                border:1px solid {BORDER}; border-radius:4px; padding:0 10px;
            }}
            QLineEdit:focus {{ border:1px solid {ACCENT}; }}
        """)
        return inp

    def _on_provider_changed(self, provider: str):
        self._provider = provider
        cfg = _PROVIDER_DEFAULTS[provider]
        self._key_label.setText(f"{cfg['label']} — API Key")
        self.key_input.setPlaceholderText(cfg["key_hint"])
        self.key_input.clear()
        self._key_doc.setText(cfg["key_doc"])
        self.url_input.setPlaceholderText(cfg["url_hint"])
        self.url_input.setText(cfg["url_prefill"])
        self.model_input.setPlaceholderText(cfg["model_hint"])
        self.model_input.clear()
        self.error_lbl.setText("")

    def _on_confirm(self):
        key = self.key_input.text().strip()
        if not key:
            self.error_lbl.setText("请填写 API Key")
            return
        save_config(self._provider, key,
                    self.url_input.text().strip(),
                    self.model_input.text().strip())
        self.accept()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{ background:{BG}; }}
            QRadioButton {{ color:{TEXT}; spacing:6px; }}
            QRadioButton::indicator {{
                width:14px; height:14px; border-radius:7px;
                border:2px solid {BORDER}; background:{INPUT};
            }}
            QRadioButton::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}
            QPushButton {{
                background:{ACCENT}; color:#000000;
                border:none; border-radius:4px; font-weight:bold;
            }}
            QPushButton:hover {{ background:#00cc66; }}
            QPushButton:pressed {{ background:#009944; }}
        """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = SetupWizard()
    w.show()
    sys.exit(app.exec())
