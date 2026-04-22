import requests
from config import OPENWEATHER_API_KEY


def get_weather(city: str) -> dict:
    """
    获取城市当前天气
    返回结构化数据，API Key 未配置时返回模拟数据
    """
    if not OPENWEATHER_API_KEY:
        return _mock_weather(city)

    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": OPENWEATHER_API_KEY,
            "units": "metric",
            "lang": "zh_cn"
        }
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()

        if resp.status_code != 200:
            return _mock_weather(city)

        return {
            "city": city,
            "description": data["weather"][0]["description"],
            "temp": round(data["main"]["temp"]),
            "feels_like": round(data["main"]["feels_like"]),
            "humidity": data["main"]["humidity"],
            "weather_main": data["weather"][0]["main"].lower(),  # clear/clouds/rain/snow 等
        }
    except Exception:
        return _mock_weather(city)


def _mock_weather(city: str) -> dict:
    return {
        "city": city,
        "description": "晴天（模拟数据，请配置 OPENWEATHER_API_KEY）",
        "temp": 22,
        "feels_like": 21,
        "humidity": 50,
        "weather_main": "clear",
    }
