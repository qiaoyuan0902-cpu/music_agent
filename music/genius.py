import requests
from bs4 import BeautifulSoup
from config import GENIUS_API_KEY

_BASE = "https://api.genius.com"


def get_lyrics(song: str, artist: str = "") -> dict:
    """获取歌词，返回歌词文本或错误信息"""
    if not GENIUS_API_KEY:
        return {"error": "Genius API Key 未配置，请在 .env 中填写 GENIUS_API_KEY"}

    query = f"{song} {artist}".strip()
    headers = {"Authorization": f"Bearer {GENIUS_API_KEY}"}

    # 搜索歌曲
    resp = requests.get(
        f"{_BASE}/search",
        headers=headers,
        params={"q": query},
        timeout=10
    )
    hits = resp.json().get("response", {}).get("hits", [])
    if not hits:
        return {"error": f"未找到《{song}》的歌词"}

    song_url = hits[0]["result"]["url"]
    song_title = hits[0]["result"]["full_title"]

    # 爬取歌词页面
    lyrics = _scrape_lyrics(song_url)
    return {"title": song_title, "lyrics": lyrics, "source_url": song_url}


def _scrape_lyrics(url: str) -> str:
    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        soup = BeautifulSoup(resp.text, "html.parser")
        # Genius 歌词容器
        containers = soup.find_all("div", attrs={"data-lyrics-container": "true"})
        if not containers:
            return "（歌词解析失败，请访问 Genius 网站查看）"
        lines = []
        for container in containers:
            for br in container.find_all("br"):
                br.replace_with("\n")
            lines.append(container.get_text())
        return "\n".join(lines).strip()
    except Exception as e:
        return f"（歌词获取失败：{e}）"
