import json
from config import PROFILE_PATH

_DEFAULT_PROFILE = {
    "liked_genres": [],        # 喜欢的音乐风格，如 ["pop", "jazz", "indie"]
    "liked_artists": [],       # 喜欢的艺术家
    "disliked_genres": [],     # 不喜欢的风格
    "mood_preferences": {},    # 情绪→风格映射，如 {"sad": ["blues", "acoustic"]}
    "language_preference": "chinese",  # 偏好语言
    "notes": ""                # 其他备注，Agent 自由填写
}


def load() -> dict:
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 补全缺失字段
        for k, v in _DEFAULT_PROFILE.items():
            data.setdefault(k, v)
        return data
    return dict(_DEFAULT_PROFILE)


def save(profile: dict):
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def merge_update(updates: dict):
    """合并更新画像，列表字段去重追加，字符串字段直接覆盖"""
    profile = load()
    for key, value in updates.items():
        if key not in profile:
            continue
        if isinstance(profile[key], list) and isinstance(value, list):
            combined = profile[key] + [v for v in value if v not in profile[key]]
            profile[key] = combined[:30]  # 最多保留 30 条
        elif isinstance(profile[key], dict) and isinstance(value, dict):
            profile[key].update(value)
        else:
            profile[key] = value
    save(profile)
    return profile


def to_summary(profile: dict) -> str:
    """生成供 system prompt 使用的画像摘要"""
    parts = []
    if profile["liked_genres"]:
        parts.append(f"喜欢的音乐风格：{', '.join(profile['liked_genres'])}")
    if profile["liked_artists"]:
        parts.append(f"喜欢的艺术家：{', '.join(profile['liked_artists'])}")
    if profile["disliked_genres"]:
        parts.append(f"不喜欢：{', '.join(profile['disliked_genres'])}")
    if profile["notes"]:
        parts.append(f"备注：{profile['notes']}")
    return "；".join(parts) if parts else "暂无偏好记录"
