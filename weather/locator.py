import requests

_QWEATHER_HOST = "p24wcv8myb.re.qweatherapi.com"
_QWEATHER_KEY  = "9ecd9e9e7237402ea98698d4bac6ef69"


def get_location_id() -> str:
    """通过 IP 定位城市，返回和风天气 location ID"""
    try:
        resp = requests.get("http://ip-api.com/json/", timeout=5)
        data = resp.json()
        if data.get("status") != "success":
            return "101020100"
        city = data.get("city", "Shanghai")

        geo = requests.get(
            f"https://{_QWEATHER_HOST}/geo/v2/city/lookup",
            params={"location": city, "lang": "zh"},
            headers={"X-QW-Api-Key": _QWEATHER_KEY},
            timeout=5,
        )
        geo_data = geo.json()
        if geo_data.get("code") == "200" and geo_data.get("location"):
            return geo_data["location"][0]["id"]
    except Exception:
        pass
    return "101020100"
