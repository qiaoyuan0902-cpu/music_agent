import requests

_QWEATHER_HOST = "p24wcv8myb.re.qweatherapi.com"


def get_location_id() -> str:
    """通过 IP 定位城市，返回和风天气 location ID"""
    import os
    api_key = os.getenv("QWEATHER_API_KEY", "")
    try:
        # 先用 ip-api 拿英文城市名
        resp = requests.get("http://ip-api.com/json/", timeout=5)
        data = resp.json()
        if data.get("status") != "success":
            return "101020100"  # 上海 fallback
        city = data.get("city", "Shanghai")

        if not api_key:
            return "101020100"

        # 再用和风 GEO 接口把城市名转成 location ID
        geo = requests.get(
            f"https://{_QWEATHER_HOST}/geo/v2/city/lookup",
            params={"location": city, "lang": "zh"},
            headers={"X-QW-Api-Key": api_key},
            timeout=5,
        )
        geo_data = geo.json()
        if geo_data.get("code") == "200" and geo_data.get("location"):
            return geo_data["location"][0]["id"]
    except Exception:
        pass
    return "101020100"
