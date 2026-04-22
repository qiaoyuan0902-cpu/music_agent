import requests
import time
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

_token_cache = {"token": None, "expires_at": 0}


def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return ""

    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data["expires_in"] - 60
        return _token_cache["token"]
    return ""


def _headers():
    token = _get_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def search_tracks(query: str, limit: int = 5) -> list[dict]:
    """搜索歌曲，返回结构化列表"""
    headers = _headers()
    if not headers:
        return [{"error": "Spotify API Key 未配置，请在 .env 文件中填写 SPOTIFY_CLIENT_ID 和 SPOTIFY_CLIENT_SECRET"}]

    resp = requests.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": query, "type": "track", "limit": limit, "market": "CN"},
        timeout=10
    )
    if resp.status_code != 200:
        return [{"error": f"搜索失败：{resp.status_code}"}]

    items = resp.json()["tracks"]["items"]
    return [_format_track(t) for t in items]


def get_recommendations(seed_artists: list = None, seed_genres: list = None,
                        seed_tracks: list = None, limit: int = 8) -> list[dict]:
    """基于种子获取推荐歌曲"""
    headers = _headers()
    if not headers:
        return [{"error": "Spotify API Key 未配置"}]

    params = {"limit": limit, "market": "CN"}
    if seed_artists:
        params["seed_artists"] = ",".join(seed_artists[:2])
    if seed_genres:
        params["seed_genres"] = ",".join(seed_genres[:3])
    if seed_tracks:
        params["seed_tracks"] = ",".join(seed_tracks[:2])

    resp = requests.get(
        "https://api.spotify.com/v1/recommendations",
        headers=headers,
        params=params,
        timeout=10
    )
    if resp.status_code != 200:
        return [{"error": f"推荐失败：{resp.status_code}"}]

    return [_format_track(t) for t in resp.json()["tracks"]]


def get_artist_top_tracks(artist_name: str) -> list[dict]:
    """获取艺术家热门歌曲"""
    headers = _headers()
    if not headers:
        return [{"error": "Spotify API Key 未配置"}]

    # 先搜索艺术家 ID
    resp = requests.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params={"q": artist_name, "type": "artist", "limit": 1},
        timeout=10
    )
    artists = resp.json().get("artists", {}).get("items", [])
    if not artists:
        return [{"error": f"未找到艺术家：{artist_name}"}]

    artist_id = artists[0]["id"]
    resp2 = requests.get(
        f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
        headers=headers,
        params={"market": "CN"},
        timeout=10
    )
    return [_format_track(t) for t in resp2.json().get("tracks", [])[:8]]


def _format_track(t: dict) -> dict:
    return {
        "name": t["name"],
        "artist": ", ".join(a["name"] for a in t["artists"]),
        "album": t["album"]["name"],
        "preview_url": t.get("preview_url"),
        "spotify_url": t["external_urls"].get("spotify"),
        "duration_ms": t["duration_ms"],
    }
