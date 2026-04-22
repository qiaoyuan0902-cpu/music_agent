import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────
# 支持 ANTHROPIC_AUTH_TOKEN（Bilibili 内部代理）或标准 ANTHROPIC_API_KEY
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
GENIUS_API_KEY = os.getenv("GENIUS_API_KEY", "")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

# ── 模型配置 ──────────────────────────────────────────────
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "20"))

# ── 数据存储路径 ──────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PROFILE_PATH = DATA_DIR / "user_profile.json"
DB_PATH = DATA_DIR / "conversations.db"
