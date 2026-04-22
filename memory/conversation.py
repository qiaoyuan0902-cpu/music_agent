import sqlite3
import json
from datetime import datetime
from config import DB_PATH, MAX_HISTORY_TURNS

# 当前登录用户 uid，0 表示未登录/匿名
_current_uid: int = 0


def set_user(uid: int):
    """切换当前用户，后续读写都隔离到该 uid"""
    global _current_uid
    _current_uid = uid or 0


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_playlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid INTEGER NOT NULL DEFAULT 0,
            song_id INTEGER,
            name TEXT NOT NULL,
            artist TEXT NOT NULL DEFAULT '',
            meta TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
    """)
    # 兼容旧表（无 uid 列）：尝试加列，已存在则忽略
    try:
        conn.execute("ALTER TABLE conversations ADD COLUMN uid INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass
    conn.commit()
    return conn


def save_turn(role: str, content: str):
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (uid, role, content, created_at) VALUES (?, ?, ?, ?)",
            (_current_uid, role, content, datetime.now().isoformat())
        )


def load_recent(n: int = MAX_HISTORY_TURNS) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE uid=? ORDER BY id DESC LIMIT ?",
            (_current_uid, n * 2)
        ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def clear_history():
    """清空当前用户的对话记录"""
    with _get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE uid=?", (_current_uid,))


# ── AI 点歌持久化 ─────────────────────────────────────────

def save_ai_song(song: dict):
    """保存 AI 点播的歌曲，同一首歌不重复存"""
    sid = song.get("id")
    with _get_conn() as conn:
        if sid:
            exists = conn.execute(
                "SELECT 1 FROM ai_playlist WHERE uid=? AND song_id=?",
                (_current_uid, sid)
            ).fetchone()
            if exists:
                return
        meta = json.dumps({k: v for k, v in song.items()
                           if k not in ("id", "name", "artist")},
                          ensure_ascii=False)
        conn.execute(
            "INSERT INTO ai_playlist (uid, song_id, name, artist, meta, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_current_uid, sid, song.get("name", ""), song.get("artist", ""),
             meta, datetime.now().isoformat())
        )


def load_ai_songs() -> list[dict]:
    """加载当前用户的 AI 点歌列表，按点播顺序返回"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT song_id, name, artist, meta FROM ai_playlist "
            "WHERE uid=? ORDER BY id ASC",
            (_current_uid,)
        ).fetchall()
    result = []
    for song_id, name, artist, meta_str in rows:
        try:
            extra = json.loads(meta_str)
        except Exception:
            extra = {}
        song = {"id": song_id, "name": name, "artist": artist, **extra}
        result.append(song)
    return result


def clear_ai_songs():
    """清空当前用户的 AI 点歌列表"""
    with _get_conn() as conn:
        conn.execute("DELETE FROM ai_playlist WHERE uid=?", (_current_uid,))
