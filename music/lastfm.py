import requests
from config import LASTFM_API_KEY

_BASE = "https://ws.audioscrobbler.com/2.0/"


def _call(method: str, **params) -> dict:
    if not LASTFM_API_KEY:
        return {"error": "Last.fm API Key 未配置，请在 .env 中填写 LASTFM_API_KEY"}
    p = {"method": method, "api_key": LASTFM_API_KEY, "format": "json", **params}
    resp = requests.get(_BASE, params=p, timeout=10)
    return resp.json()


def get_similar_artists(artist: str, limit: int = 6) -> list[dict]:
    data = _call("artist.getSimilar", artist=artist, limit=limit)
    if "error" in data:
        return [data]
    artists = data.get("similarartists", {}).get("artist", [])
    return [{"name": a["name"], "match": float(a["match"])} for a in artists]


def get_top_tracks_by_tag(tag: str, limit: int = 8) -> list[dict]:
    """按风格标签获取热门歌曲"""
    data = _call("tag.getTopTracks", tag=tag, limit=limit)
    if "error" in data:
        return [data]
    tracks = data.get("tracks", {}).get("track", [])
    return [{"name": t["name"], "artist": t["artist"]["name"]} for t in tracks]


def get_artist_info(artist: str) -> dict:
    data = _call("artist.getInfo", artist=artist, lang="zh")
    if "error" in data:
        return data
    info = data.get("artist", {})
    tags = [t["name"] for t in info.get("tags", {}).get("tag", [])]
    return {
        "name": info.get("name"),
        "tags": tags,
        "summary": info.get("bio", {}).get("summary", "")[:300],
    }
