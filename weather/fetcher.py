import os
import requests

_QWEATHER_HOST = "p24wcv8myb.re.qweatherapi.com"

# icon code → weather_main (matches existing emoji map in qt_app.py)
def _icon_to_main(icon: str) -> str:
    code = int(icon) if icon.isdigit() else 0
    if code == 100:
        return "clear"
    if code in (101, 102, 103, 104):
        return "clouds"
    if 300 <= code <= 399:
        return "rain"
    if 400 <= code <= 499:
        return "snow"
    if 500 <= code <= 599:
        return "mist"
    if code in (200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213):
        return "thunderstorm"
    return "clouds"


def get_weather(location_id: str) -> dict:
    api_key = os.getenv("QWEATHER_API_KEY", "")
    if not api_key:
        return _mock_weather(location_id)

    try:
        resp = requests.get(
            f"https://{_QWEATHER_HOST}/v7/weather/now",
            params={"location": location_id, "lang": "zh", "unit": "m"},
            headers={"X-QW-Api-Key": api_key},
            timeout=8,
        )
        data = resp.json()
        if data.get("code") != "200":
            return _mock_weather(location_id)

        now = data["now"]
        return {
            "city":         location_id,
            "description":  now.get("text", ""),
            "temp":         int(now.get("temp", 0)),
            "feels_like":   int(now.get("feelsLike", 0)),
            "humidity":     int(now.get("humidity", 0)),
            "weather_main": _icon_to_main(now.get("icon", "101")),
        }
    except Exception:
        return _mock_weather(location_id)


def _mock_weather(location_id: str) -> dict:
    return {
        "city":         location_id,
        "description":  "晴天（模拟数据）",
        "temp":         22,
        "feels_like":   21,
        "humidity":     50,
        "weather_main": "clear",
    }
