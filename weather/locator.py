import requests


def get_city_by_ip() -> str:
    """通过 IP 自动定位城市，无需 API Key"""
    try:
        resp = requests.get("http://ip-api.com/json/?lang=zh-CN", timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return data.get("city", "未知城市")
    except Exception:
        pass
    return "北京"  # 定位失败时的默认城市
