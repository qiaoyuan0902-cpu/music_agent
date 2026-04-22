"""
网易云音乐接入模块
- 二维码扫码登录，Cookie 持久化到 data/netease_cookie.json
- 获取「我喜欢的音乐」歌单
"""
import json
import time
from pathlib import Path
from pyncm import apis, GetCurrentSession, SetCurrentSession, DumpSessionAsString, LoadSessionFromString

COOKIE_PATH = Path(__file__).parent.parent / "data" / "netease_cookie.json"


# ── Session 持久化 ────────────────────────────────────────

def save_session():
    COOKIE_PATH.parent.mkdir(exist_ok=True)
    # DumpSessionAsString 需要显式传入当前 session
    COOKIE_PATH.write_text(DumpSessionAsString(GetCurrentSession()))


def load_session() -> bool:
    """尝试从本地加载 session，返回是否成功"""
    if not COOKIE_PATH.exists():
        return False
    try:
        session = LoadSessionFromString(COOKIE_PATH.read_text())
        SetCurrentSession(session)
        result = apis.login.GetCurrentLoginStatus()
        # 响应结构: {"code":200, "profile": {...}, "account": {...}}
        if result.get("profile"):
            return True
    except Exception:
        pass
    return False


# ── 二维码登录 ────────────────────────────────────────────

def get_qr_code() -> tuple[str, str]:
    """
    返回 (unikey, qr_url)
    qr_url 是可以直接生成二维码的链接
    """
    result = apis.login.LoginQrcodeUnikey()
    unikey = result["unikey"]
    qr_url = apis.login.GetLoginQRCodeUrl(unikey)
    return unikey, qr_url


def poll_qr_login(unikey: str) -> dict:
    """
    轮询二维码状态
    返回 {"code": 800/801/802/803, "message": str}
    800 = 二维码过期
    801 = 等待扫码
    802 = 已扫码，等待确认
    803 = 登录成功
    """
    result = apis.login.LoginQrcodeCheck(unikey)
    code = result.get("code", 800)
    messages = {
        800: "二维码已过期，请刷新",
        801: "等待扫码...",
        802: "已扫码，请在手机上确认",
        803: "登录成功",
    }
    if code == 803:
        save_session()
    return {"code": code, "message": messages.get(code, "未知状态")}


# ── 获取用户信息 ──────────────────────────────────────────

def get_user_profile() -> dict:
    """返回当前登录用户的基本信息"""
    try:
        result = apis.login.GetCurrentLoginStatus()
        # 响应结构: {"code":200, "profile": {...}, "account": {...}}
        profile = result.get("profile") or {}
        return {
            "uid":      profile.get("userId", 0),
            "nickname": profile.get("nickname", "未知用户"),
            "avatar":   profile.get("avatarUrl", ""),
        }
    except Exception:
        return {"uid": 0, "nickname": "未登录", "avatar": ""}


# ── 获取「我喜欢的音乐」歌单 ──────────────────────────────

def get_liked_songs(limit: int = 50) -> list[dict]:
    """
    获取「我喜欢的音乐」歌单，返回歌曲列表
    每项: {id, name, artist, album, duration_ms}
    """
    try:
        profile = get_user_profile()
        uid = profile["uid"]
        if not uid:
            return []

        # 获取用户所有歌单，第一个就是「我喜欢的音乐」
        playlists = apis.user.GetUserPlaylists(uid)
        liked_id = playlists["playlist"][0]["id"]

        # 拉取歌单所有曲目
        tracks_data = apis.playlist.GetPlaylistAllTracks(liked_id)
        songs = []
        for t in tracks_data["songs"][:limit]:
            artists = "/".join(a["name"] for a in t.get("ar", []))
            songs.append({
                "id":          t["id"],
                "name":        t["name"],
                "artist":      artists,
                "album":       t.get("al", {}).get("name", ""),
                "duration_ms": t.get("dt", 0),
            })
        return songs
    except Exception as e:
        return []


def search_netease(query: str, limit: int = 5) -> list[dict]:
    """搜索网易云歌曲，返回 [{id, name, artist, album, duration_ms}]"""
    try:
        r = apis.cloudsearch.GetSearchResult(query, stype=1, limit=limit, offset=0)
        songs = []
        for s in r.get("result", {}).get("songs", []):
            artists = "/".join(a["name"] for a in s.get("ar", []))
            songs.append({
                "id":          s["id"],
                "name":        s["name"],
                "artist":      artists,
                "album":       s.get("al", {}).get("name", ""),
                "duration_ms": s.get("dt", 0),
            })
        return songs
    except Exception:
        return []


def get_song_url(song_id: int, bitrate: int = 128000) -> str:
    """获取歌曲播放 URL，失败返回空字符串"""
    try:
        result = apis.track.GetTrackAudio([song_id], bitrate=bitrate)
        data = result.get("data", [])
        if data and data[0].get("url"):
            return data[0]["url"]
    except Exception:
        pass
    return ""


def fmt_duration(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"

