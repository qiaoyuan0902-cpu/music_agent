from datetime import datetime
from weather.locator import get_location_id
from weather.fetcher import get_weather
from weather.mood_mapper import weather_to_prompt_text
from memory import profile as profile_store

_loc_cache = {"id": None}


def build_system_prompt() -> str:
    # 天气信息
    if not _loc_cache["id"]:
        _loc_cache["id"] = get_location_id()
    weather = get_weather(_loc_cache["id"])
    weather_text = weather_to_prompt_text(weather)

    # 用户画像
    user_profile = profile_store.load()
    profile_text = profile_store.to_summary(user_profile)

    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    return f"""你是一个 24 小时全天候的 AI 音乐伴侣，名叫「Claudio」。

## 当前信息
- 时间：{now}
- {weather_text}
- 用户音乐偏好：{profile_text}

## 你的能力
1. **自由聊天**：可以聊音乐、聊心情、聊生活，像朋友一样陪伴用户
2. **音乐搜索**：帮用户找到想听的歌曲
3. **智能推荐**：结合当前天气、用户心情和音乐品味，推荐最合适的音乐
4. **歌词查询**：获取歌词，一起感受歌词的意境
5. **艺术家探索**：介绍艺术家、推荐相似艺术家
6. **学习偏好**：在对话中记住用户的音乐喜好，持续优化推荐

## 行为准则
- 用中文回复，语气温暖自然，像一个懂音乐的朋友
- 主动结合天气和时间推荐音乐（比如雨天推荐适合雨天的歌）
- 当用户表达喜好时（"我喜欢..."、"这首歌真好听"），主动调用 update_user_profile 记录
- 推荐音乐时，简短说明为什么推荐这首歌，让推荐有温度
- 如果 API 未配置，诚实告知用户，但仍然可以聊天和给出建议
- 不要一次推荐太多歌，3-5 首最合适，质量优于数量
"""
