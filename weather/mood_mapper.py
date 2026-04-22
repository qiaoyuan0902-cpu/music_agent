# 天气状态 → 音乐情绪/风格映射
WEATHER_MOOD_MAP = {
    "clear": {
        "mood": "愉快、充满活力",
        "genres": ["pop", "indie pop", "dance", "funk"],
        "description": "阳光明媚"
    },
    "clouds": {
        "mood": "平静、思考",
        "genres": ["indie", "alternative", "acoustic", "lo-fi"],
        "description": "多云"
    },
    "rain": {
        "mood": "慵懒、感性、内省",
        "genres": ["jazz", "blues", "acoustic", "soul", "ambient"],
        "description": "下雨"
    },
    "drizzle": {
        "mood": "温柔、慵懒",
        "genres": ["acoustic", "bossa nova", "lo-fi", "jazz"],
        "description": "小雨"
    },
    "thunderstorm": {
        "mood": "激烈、紧张",
        "genres": ["rock", "metal", "electronic", "dramatic classical"],
        "description": "雷暴"
    },
    "snow": {
        "mood": "宁静、纯净",
        "genres": ["classical", "ambient", "piano", "new age"],
        "description": "下雪"
    },
    "mist": {
        "mood": "神秘、朦胧",
        "genres": ["ambient", "dream pop", "shoegaze", "post-rock"],
        "description": "雾天"
    },
    "fog": {
        "mood": "神秘、朦胧",
        "genres": ["ambient", "dream pop", "shoegaze"],
        "description": "大雾"
    },
    "haze": {
        "mood": "沉静",
        "genres": ["lo-fi", "ambient", "chill"],
        "description": "霾"
    },
}

_DEFAULT = {
    "mood": "平静",
    "genres": ["pop", "indie"],
    "description": "未知天气"
}


def get_music_mood(weather_main: str) -> dict:
    """根据天气状态返回推荐音乐情绪和风格"""
    return WEATHER_MOOD_MAP.get(weather_main.lower(), _DEFAULT)


def weather_to_prompt_text(weather: dict) -> str:
    """生成供 system prompt 使用的天气摘要"""
    mood_info = get_music_mood(weather.get("weather_main", ""))
    return (
        f"当前天气：{weather['city']} {weather['description']}，"
        f"{weather['temp']}°C，湿度 {weather['humidity']}%。"
        f"适合的音乐情绪：{mood_info['mood']}，"
        f"推荐风格：{', '.join(mood_info['genres'])}。"
    )
