import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── 用户数据目录（打包后写这里，开发时写项目目录）────────────
def _user_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        # 打包后：写到系统用户数据目录
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "ClaudioFM"
        elif sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home())) / "ClaudioFM"
        else:
            base = Path.home() / ".claudiofm"
    else:
        # 开发时：项目目录
        base = Path(__file__).parent
    base.mkdir(parents=True, exist_ok=True)
    return base

USER_DATA_DIR = _user_data_dir()

# 优先加载用户数据目录的 .env，再 fallback 到项目目录
_env_candidates = [USER_DATA_DIR / ".env", Path(__file__).parent / ".env"]
for _p in _env_candidates:
    if _p.exists():
        load_dotenv(_p)
        break

# ── API Keys ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY", "")

# ── 模型配置 ──────────────────────────────────────────────
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))

# ── 数据存储路径 ──────────────────────────────────────────
DATA_DIR = USER_DATA_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
PROFILE_PATH = DATA_DIR / "user_profile.json"
DB_PATH = DATA_DIR / "conversations.db"
