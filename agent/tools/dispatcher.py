import json
from music.netease import search_netease
from weather.locator import get_location_id
from weather.fetcher import get_weather
from weather.mood_mapper import weather_to_prompt_text
from memory import profile as profile_store


def dispatch(tool_name: str, tool_input: dict) -> str:
    try:
        result = _execute(tool_name, tool_input)
    except Exception as e:
        result = {"error": f"工具执行出错：{e}"}
    return json.dumps(result, ensure_ascii=False, indent=2)


def _execute(tool_name: str, inp: dict):
    if tool_name == "play_song":
        query = inp["song_name"]
        if inp.get("artist"):
            query = f"{query} {inp['artist']}"
        songs = search_netease(query, limit=1)
        if not songs:
            return {"error": "未找到该歌曲，请换个关键词试试"}
        return {"__play__": True, **songs[0]}

    elif tool_name == "switch_tts_voice":
        from ui.qt_app import VOICES
        name = inp.get("voice_name", "")
        voice_id = VOICES.get(name)
        if not voice_id:
            name_lower = name.lower()
            if "男" in name_lower:
                voice_id = "zh-CN-YunxiNeural"; name = "云希"
            elif "女" in name_lower:
                voice_id = "zh-CN-XiaoxiaoNeural"; name = "晓晓"
            elif "粤" in name_lower or "广东" in name_lower:
                voice_id = "zh-HK-HiuGaaiNeural"; name = "晓佳"
            elif "台" in name_lower:
                voice_id = "zh-TW-HsiaoChenNeural"; name = "晓臻"
            elif "东北" in name_lower:
                voice_id = "zh-CN-liaoning-XiaobeiNeural"; name = "小北"
            else:
                return {"error": f"未找到声音'{name}'，可用：晓晓、晓伊、小北、小妮、云希、云健、云夏、云扬、晓佳、云龙、晓臻、云哲"}
        return {"__switch_voice__": True, "voice_id": voice_id, "voice_name": name}

    elif tool_name == "get_current_weather":
        loc = inp.get("city") or get_location_id()
        weather = get_weather(loc)
        return {**weather, "music_suggestion": weather_to_prompt_text(weather)}

    elif tool_name == "update_user_profile":
        updates = {k: v for k, v in inp.items() if v}
        updated = profile_store.merge_update(updates)
        return {"status": "已更新用户偏好", "profile_summary": profile_store.to_summary(updated)}

    else:
        return {"error": f"未知工具：{tool_name}"}
